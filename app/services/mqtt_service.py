# app/services/mqtt_service.py
import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..mqtt_client import mqtt_client
from ..models.ingestas import Ingesta
from ..services.opcua_service import OPCUAService # <--- NUEVO
from ..config import settings # <--- NUEVO

logger = logging.getLogger("mqtt_service")

# Variable global para manejar la conexión de escritura OPC UA
_opcua_writer: Optional[OPCUAService] = None

def _persist_measurement(payload: dict):
    # ... Tu lógica de persistencia de datos (Ingesta) se mantiene aquí ...
    db: Session = SessionLocal()
    try:
        # Extraemos datos del JSON
        asset_codigo = payload.get("asset_codigo")
        motor_codigo = payload.get("motor_codigo")
        variable = payload.get("variable")
        valor = payload.get("valor")
        ts_utc_str = payload.get("ts_utc")
        
        if not variable or valor is None:
            return

        ts_utc = datetime.fromisoformat(ts_utc_str) if ts_utc_str else datetime.utcnow()

        ingesta = Ingesta(
            asset_codigo=asset_codigo,
            motor_codigo=motor_codigo,
            variable=variable,
            valor=float(valor),
            ts_utc=ts_utc,
            archivo_origen="MQTT_REALTIME"
        )
        
        db.add(ingesta)
        db.commit()

    except Exception as e:
        logger.error(f"Error guardando ingesta MQTT en BD: {e}")
        db.rollback()
    finally:
        db.close()

# --- NUEVA FUNCIÓN PARA EJECUTAR EL COMANDO ---
def _execute_opcua_write(node_id: str, valor: str):
    """Lógica para conectar, escribir y desconectar del PLC para un comando."""
    global _opcua_writer
    try:
        if _opcua_writer is None:
            # Inicializar el cliente OPC UA con el endpoint de settings
            _opcua_writer = OPCUAService(settings.OPCUA_ENDPOINT)
        
        _opcua_writer.connect()
        # Llama a la nueva función de escritura en el servicio
        _opcua_writer.write_node_value(node_id, valor)
        
    except Exception as e:
        # Los errores de escritura deben ser reportados aquí
        logger.error(f"Fallo crítico al ejecutar comando OPC UA: {e}")
    finally:
        # Se desconecta después de cada comando para liberar recursos del PLC
        if _opcua_writer:
            _opcua_writer.disconnect()
        # Se puede establecer en None para forzar una reconexión completa en el siguiente comando
        _opcua_writer = None 


def init_subscriptions():
    """Inicia los listeners de MQTT."""
    
    def on_message(client, userdata, msg):
        try:
            topic = msg.topic
            payload_str = msg.payload.decode(errors='ignore')
            data = json.loads(payload_str)
            
            # RUTA 1: COMANDOS DE CONTROL (tesis/cmd/opcua/write) <--- AQUÍ ESTÁ LA LÓGICA DE CONTROL
            if topic == "tesis/cmd/opcua/write":
                logger.warning(f"[CMD] Recibido comando de escritura: {data}")
                node_id = data.get("node_id")
                valor = data.get("valor")
                if node_id and valor is not None:
                    _execute_opcua_write(node_id, valor)
                
            # RUTA 2: MEDICIONES OPC UA ENTRANTES (tesis/opcua/medicion)
            elif topic == "tesis/opcua/medicion":
                _persist_measurement(data)
                
        except json.JSONDecodeError:
            logger.error(f"Error de formato JSON en mensaje: {payload_str}")
        except Exception as e:
            logger.exception(f"Error procesando mensaje MQTT: {e}")

    # Asignar el callback
    mqtt_client.client.on_message = on_message
    
    # Suscribirse a los temas relevantes
    mqtt_client.client.subscribe([
        ("tesis/cmd/opcua/write", 1), # QoS 1 para comandos importantes
        ("tesis/opcua/medicion", 0)
    ])
    
    logger.info("Suscripciones MQTT iniciadas: mediciones y comandos de escritura")