# app/services/opcua_ingestor.py
import logging
import threading
import datetime
import time
import random
from typing import Optional

from ..config import settings
from ..mqtt_client import mqtt_client
from .opcua_service import OPCUAService

logger = logging.getLogger("opcua_ingestor")

_opcua: Optional[OPCUAService] = None
_stop_flag: bool = False
_timer_ref: Optional[threading.Timer] = None


def _enabled() -> bool:
    try:
        return bool(getattr(settings, "OPCUA_INGEST_ENABLED", False))
    except Exception:
        return False


def _get_client() -> OPCUAService:
    """Obtiene cliente OPC UA conectado una vez."""
    global _opcua
    if _opcua is None:
        _opcua = OPCUAService(settings.OPCUA_ENDPOINT)
        _opcua.connect()
    return _opcua


def _ensure_connected_with_backoff() -> OPCUAService:
    """Asegura sesión viva con backoff exponencial."""
    global _opcua
    backoff, max_backoff = 1.0, 60.0
    while True:
        try:
            if _opcua is None:
                _opcua = OPCUAService(settings.OPCUA_ENDPOINT)
            # Si tu OPCUAService no tiene is_connected(), se puede eliminar esto
            if hasattr(_opcua, "is_connected") and not _opcua.is_connected():
                _opcua.connect()
            # Ping para validar sesión (si no existe ping(), comentar esta línea)
            if hasattr(_opcua, "ping"):
                _opcua.ping()
            return _opcua
        except Exception as e:
            logger.warning(f"OPC UA reconnect in {backoff:.1f}s: {e}")
            try:
                if _opcua:
                    _opcua.disconnect()
            except Exception:
                pass
            _opcua = None
            time.sleep(backoff)
            backoff = min(max_backoff, backoff * 2 + random.random())


def _tick():
    """
    Lee nodos OPC UA y publica por MQTT para monitoreo.
    NO escribe en BD.
    Puede resolver asset/motor desde BD a partir de despliegue_id.
    """
    global _timer_ref, _stop_flag, _opcua
    if _stop_flag or not _enabled():
        return

    try:
        client = _ensure_connected_with_backoff()
        nodes = getattr(settings, "opcua_nodes", [])
        now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

        if not nodes:
            logger.warning("OPCUA_NODES_JSON vacío; no hay nodos que leer")
          
            if not _stop_flag and _enabled():
                _timer_ref = threading.Timer(
                    max(30, settings.OPCUA_INGEST_INTERVAL_SEC * 6),
                    _tick
                )
                _timer_ref.daemon = True
                _timer_ref.start()
            return

        # Por defecto: resolver SIEMPRE desde BD (pensado a futuro)
        resolve_from_db = bool(getattr(settings, "OPCUA_RESOLVE_FROM_DB", True))
        if resolve_from_db:
            from sqlalchemy.orm import Session
            from ..database import SessionLocal
            from ..models.despliegues import Despliegue
            from ..models.assets import Asset
            from ..models.motores import Motor

            def _resolve_asset_motor_from_despliegue(db: Session, despliegue_id: int):
                d = (
                    db.query(Despliegue, Asset, Motor)
                    .join(Asset, Asset.asset_id == Despliegue.asset_id)
                    .join(Motor, Motor.motor_id == Despliegue.motor_id)
                    .filter(Despliegue.despliegue_id == despliegue_id)
                    .first()
                )
                if not d:
                    return (None, None)
                _, a, m = d
                return (a.asset_codigo, m.motor_codigo)

            db: Optional[Session] = SessionLocal()
        else:
            db = None
            _resolve_asset_motor_from_despliegue = None  # type: ignore

        try:
            for n in nodes:
                if not _enabled() or _stop_flag:
                    return

                node_id = n.get("node_id")
                variable = n.get("variable")
                if not node_id or not variable:
                    logger.warning(f"Nodo inválido en OPCUA_NODES_JSON: {n}")
                    continue

                # Leer valor OPC UA
                try:
                    value = client.read_node_value(node_id)
                except Exception as e:
                    logger.warning(f"Fallo leyendo nodo {node_id}: {e}")
                    try:
                        if _opcua:
                            _opcua.disconnect()
                    except Exception:
                        pass
                    _opcua = None
                    break  # salta a próximo ciclo

                # Se asume que el JSON trae SOLO despliegue_id y opcional indicador_calidad
                despliegue_id = n.get("despliegue_id")
                indicador_calidad = n.get("indicador_calidad", 0)

                asset_codigo = None
                motor_codigo = None

                # Resolver siempre desde BD si está habilitado y hay despliegue_id
                if resolve_from_db and despliegue_id is not None:
                    try:
                        ac, mc = _resolve_asset_motor_from_despliegue(db, int(despliegue_id))  # type: ignore
                        asset_codigo = ac
                        motor_codigo = mc
                    except Exception as e:
                        logger.warning(
                            f"No se pudo resolver asset/motor para despliegue_id={despliegue_id}: {e}"
                        )

                # Publicación MQTT opcional
                if getattr(settings, "OPCUA_INGEST_PUBLISH_MQTT", False):
                    payload = {
                        "asset_codigo": asset_codigo,
                        "motor_codigo": motor_codigo,
                        "despliegue_id": despliegue_id,
                        "variable": variable,
                        "valor": value,
                        "indicador_calidad": indicador_calidad,
                        "ts_utc": now_utc.replace(microsecond=0).isoformat(),
                        "source": "opcua",
                    }
                    mqtt_client.publish("tesis/opcua/medicion", payload)

                logger.info(
                    f"[OPCUA] despliegue={despliegue_id} asset={asset_codigo} "
                    f"motor={motor_codigo} {variable}={value} ts={now_utc.isoformat()}"
                )

        finally:
            if db:
                db.close()

    except Exception as e:
        logger.exception(f"Error en ingestor OPC UA: {e}")
        try:
            if _opcua:
                _opcua.disconnect()
        except Exception:
            pass
        _opcua = None

    # Reprograma siguiente ciclo
    if not _stop_flag and _enabled():
        _timer_ref = threading.Timer(settings.OPCUA_INGEST_INTERVAL_SEC, _tick)
        _timer_ref.daemon = True
        _timer_ref.start()


def start_ingestor():
    """Inicia el ingestor si está habilitado en settings."""
    if not _enabled():
        logger.info("Ingestor OPC UA deshabilitado por configuración")
        return
    global _stop_flag
    _stop_flag = False
    _tick()
    logger.info("Ingestor OPC UA iniciado (solo MQTT, sin escritura en BD)")


def stop_ingestor():
    """Detiene el ingestor y cierra sesión OPC UA."""
    global _stop_flag, _timer_ref, _opcua
    _stop_flag = True
    if _timer_ref:
        _timer_ref.cancel()
        _timer_ref = None
    try:
        if _opcua:
            _opcua.disconnect()
    except Exception:
        pass
    _opcua = None
    logger.info("Ingestor OPC UA detenido")
