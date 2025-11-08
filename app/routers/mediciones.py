from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from fastapi.responses import StreamingResponse
import io, csv

from sqlalchemy import asc, desc

from ..database import get_db
from ..models.mediciones import Medicion
from ..models.despliegues import Despliegue
from ..models.assets import Asset
from ..models.motores import Motor
from ..models.variables import Variable
from ..schemas.mediciones import MedicionRead, MedicionCreate, MedicionUpdate
from ..config import settings
from ..mqtt_client import mqtt_client

router = APIRouter()

# -------------------------
# Reglas y banderas
# -------------------------
READ_ONLY = not getattr(settings, "ALLOW_WRITE_MEDICIONES", False)
MAX_LIMIT = 1000
DEFAULT_LIMIT = 100
MAX_CSV_ROWS = 50_000

def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _validate_time_window(ts_from: Optional[datetime], ts_to: Optional[datetime]):
    if ts_from and ts_to and ts_from > ts_to:
        raise HTTPException(400, "ts_from no puede ser mayor que ts_to")

def _validate_sort(sort: str, allowed: dict):
    if sort not in allowed:
        raise HTTPException(400, f"Parámetro sort inválido. Permitidos: {', '.join(allowed.keys())}")
    return allowed[sort]

def _validate_medicion_payload(db: Session, p: MedicionCreate):
    # despliegue válido
    d = db.query(Despliegue).filter(Despliegue.despliegue_id == p.despliegue_id).first()
    if not d:
        raise HTTPException(400, "despliegue_id no existe")

    # variable válida en catálogo
    if not db.query(Variable).filter(Variable.nombre == p.variable).first():
        raise HTTPException(400, "variable no registrada en catálogo de variables")

    # ts_utc obligatorio y razonable
    if not p.ts_utc:
        raise HTTPException(400, "ts_utc es obligatorio")
    now = _utc_now()
    if p.ts_utc > now + timedelta(seconds=5):
        raise HTTPException(400, "ts_utc no puede estar en el futuro")

    # si el despliegue tiene fin, ts debe estar dentro [inicio, fin]
    if d.inicio and p.ts_utc < d.inicio:
        raise HTTPException(400, "ts_utc anterior al inicio del despliegue")
    if d.fin and p.ts_utc > d.fin:
        raise HTTPException(400, "ts_utc posterior al fin del despliegue")

    # evitar duplicado exacto (despliegue_id, variable, ts_utc)
    dup = (db.query(Medicion)
             .filter(
                 Medicion.despliegue_id == p.despliegue_id,
                 Medicion.variable == p.variable,
                 Medicion.ts_utc == p.ts_utc
             ).first())
    if dup:
        raise HTTPException(409, "Medición duplicada (misma variable y ts_utc en despliegue)")

# -------------------------
# Endpoints de lectura
# -------------------------

@router.get("/latest", response_model=List[MedicionRead])
def latest_mediciones(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
):
    q = (db.query(Medicion)
           .order_by(desc(Medicion.ts_utc), desc(Medicion.medicion_id))
           .limit(_clamp_limit(limit)))
    return q.all()

@router.get("/last/{n}", response_model=List[MedicionRead])
def last_n_mediciones(n: int, db: Session = Depends(get_db)):
    q = (db.query(Medicion)
           .order_by(desc(Medicion.ts_utc), desc(Medicion.medicion_id))
           .limit(_clamp_limit(n)))
    return q.all()

@router.get("/", response_model=List[MedicionRead])
def list_mediciones(
    asset_codigo: Optional[str] = Query(None),
    motor_codigo: Optional[str] = Query(None),
    variable: Optional[str] = Query(None),
    ts_from: Optional[datetime] = Query(None),
    ts_to: Optional[datetime] = Query(None),
    sort: str = Query("-ts_utc"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _validate_time_window(ts_from, ts_to)

    q = (db.query(Medicion)
           .join(Despliegue, Medicion.despliegue_id == Despliegue.despliegue_id)
           .join(Asset, Despliegue.asset_id == Asset.asset_id)
           .join(Motor, Despliegue.motor_id == Motor.motor_id))

    if asset_codigo:
        q = q.filter(Asset.asset_codigo == asset_codigo)
    if motor_codigo:
        q = q.filter(Motor.motor_codigo == motor_codigo)
    if variable:
        q = q.filter(Medicion.variable == variable)
    if ts_from:
        q = q.filter(Medicion.ts_utc >= ts_from)
    if ts_to:
        q = q.filter(Medicion.ts_utc <= ts_to)

    sort_map = {
        "ts_utc": Medicion.ts_utc,
        "-ts_utc": desc(Medicion.ts_utc),
        "variable": Medicion.variable,
        "-variable": desc(Medicion.variable),
    }
    sort_col = _validate_sort(sort, sort_map)
    q = q.order_by(sort_col)

    return q.offset(offset).limit(_clamp_limit(limit)).all()

@router.get("/export/csv")
def export_mediciones_csv(
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    variable: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    _validate_time_window(ts_from, ts_to)

    q = (db.query(Medicion, Asset.asset_codigo, Motor.motor_codigo)
           .join(Despliegue, Medicion.despliegue_id == Despliegue.despliegue_id)
           .join(Asset, Despliegue.asset_id == Asset.asset_id)
           .join(Motor, Despliegue.motor_id == Motor.motor_id))

    if asset_codigo: q = q.filter(Asset.asset_codigo == asset_codigo)
    if motor_codigo: q = q.filter(Motor.motor_codigo == motor_codigo)
    if variable:     q = q.filter(Medicion.variable == variable)
    if ts_from:      q = q.filter(Medicion.ts_utc >= ts_from)
    if ts_to:        q = q.filter(Medicion.ts_utc <= ts_to)

    q = q.order_by(asc(Medicion.ts_utc)).limit(MAX_CSV_ROWS + 1)
    rows = q.all()
    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(413, f"Demasiadas filas para exportar (> {MAX_CSV_ROWS}). Aplique más filtros.")

    stream = io.StringIO()
    w = csv.writer(stream)
    w.writerow(["medicion_id","asset_codigo","motor_codigo","ts_utc","ts_local_tz","variable","valor","archivo_origen","importado_en"])
    for m, a_code, m_code in rows:
        w.writerow([m.medicion_id, a_code, m_code, m.ts_utc, m.ts_local_tz, m.variable, m.valor, m.archivo_origen, m.importado_en])

    stream.seek(0)
    headers = {"Content-Disposition": "attachment; filename=mediciones.csv"}
    return StreamingResponse(stream, media_type="text/csv", headers=headers)

# -------------------------
# Endpoints de escritura (opcionales / bloqueables)
# -------------------------

@router.post("/", response_model=MedicionRead, status_code=status.HTTP_201_CREATED)
def create_medicion(payload: MedicionCreate, db: Session = Depends(get_db)):
    if READ_ONLY:
        raise HTTPException(403, "Escritura de mediciones deshabilitada por política (ALLOW_WRITE_MEDICIONES=false)")
    _validate_medicion_payload(db, payload)

    m = Medicion(**payload.dict())
    db.add(m); db.commit(); db.refresh(m)

    # completar asset/motor para respuesta
    d = db.query(Despliegue).filter(Despliegue.despliegue_id == m.despliegue_id).first()
    a = db.query(Asset).filter(Asset.asset_id == d.asset_id).first() if d else None
    mo = db.query(Motor).filter(Motor.motor_id == d.motor_id).first() if d else None

    # publicar MQTT opcional (solo notificación)
    try:
        mqtt_client.publish("tesis/mediciones/nueva", {
            "medicion_id": m.medicion_id,
            "despliegue_id": m.despliegue_id,
            "variable": m.variable,
            "valor": m.valor,
            "ts_utc": m.ts_utc.isoformat()
        })
    except Exception:
        pass

    return {
        "medicion_id": m.medicion_id, "despliegue_id": m.despliegue_id, "ts_utc": m.ts_utc, "ts_local_tz": m.ts_local_tz,
        "variable": m.variable, "valor": m.valor, "archivo_origen": m.archivo_origen, "importado_en": m.importado_en,
        "asset_codigo": a.asset_codigo if a else None, "motor_codigo": mo.motor_codigo if mo else None
    }

@router.put("/{medicion_id}", response_model=MedicionRead)
def update_medicion(medicion_id: int, payload: MedicionUpdate, db: Session = Depends(get_db)):
    if READ_ONLY:
        raise HTTPException(403, "Escritura de mediciones deshabilitada por política (ALLOW_WRITE_MEDICIONES=false)")

    m = db.query(Medicion).filter(Medicion.medicion_id == medicion_id).first()
    if not m:
        raise HTTPException(404, "Medición no encontrada")

    # inmutables
    immutable = {"ts_local_tz", "importado_en", "medicion_id"}
    for k in payload.dict(exclude_unset=True).keys():
        if k in immutable:
            raise HTTPException(400, f"No se permite modificar el campo inmutable: {k}")

    # validar con snapshot nuevo
    data = payload.dict(exclude_unset=True)
    create_like = MedicionCreate(
        despliegue_id = data.get("despliegue_id", m.despliegue_id),
        ts_utc       = data.get("ts_utc", m.ts_utc),
        variable     = data.get("variable", m.variable),
        valor        = data.get("valor", m.valor),
        archivo_origen = data.get("archivo_origen", m.archivo_origen),
    )
    _validate_medicion_payload(db, create_like)

    for k, v in data.items():
        setattr(m, k, v)
    db.commit(); db.refresh(m)

    d = db.query(Despliegue).filter(Despliegue.despliegue_id == m.despliegue_id).first()
    a = db.query(Asset).filter(Asset.asset_id == d.asset_id).first() if d else None
    mo = db.query(Motor).filter(Motor.motor_id == d.motor_id).first() if d else None

    return {
        "medicion_id": m.medicion_id, "despliegue_id": m.despliegue_id, "ts_utc": m.ts_utc, "ts_local_tz": m.ts_local_tz,
        "variable": m.variable, "valor": m.valor, "archivo_origen": m.archivo_origen, "importado_en": m.importado_en,
        "asset_codigo": a.asset_codigo if a else None, "motor_codigo": mo.motor_codigo if mo else None
    }

@router.delete("/{medicion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medicion(medicion_id: int, db: Session = Depends(get_db)):
    if READ_ONLY:
        raise HTTPException(403, "Escritura de mediciones deshabilitada por política (ALLOW_WRITE_MEDICIONES=false)")
    m = db.query(Medicion).filter(Medicion.medicion_id == medicion_id).first()
    if not m:
        raise HTTPException(404, "Medición no encontrada")
    db.delete(m); db.commit()
    return
