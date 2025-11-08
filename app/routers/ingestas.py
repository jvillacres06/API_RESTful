# app/routers/ingestas.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from fastapi.responses import StreamingResponse
import io, csv

from ..database import get_db
from ..models.ingestas import Ingesta
from ..models.assets import Asset
from ..models.motores import Motor
from ..models.variables import Variable
from ..schemas.ingestas import IngestaCreate, IngestaRead, IngestaUpdate
from ..config import settings

router = APIRouter()

# -------------------------
# Reglas de negocio
# -------------------------
MAX_LIMIT        = 1000
DEFAULT_LIMIT    = 100
MAX_CSV_ROWS     = 50_000
MAX_BACK_DAYS    = 365 * 5  # no más de 5 años atrás

# Si se requiere límites/rangos por variable, se configuran aquí (opcional)
VARIABLE_RULES: dict[str, dict] = {
    # "Counter": {"type": (int, float), "min": 0, "max": 1_000_000},
    # "Overall Vibration": {"type": (int, float), "min": 0.0, "max": 100.0},
}

def _clamp_limit(n: int) -> int:
    return max(1, min(int(n), MAX_LIMIT))

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _validate_time_window(ts_from: Optional[datetime], ts_to: Optional[datetime]):
    if ts_from and ts_to and ts_from > ts_to:
        raise HTTPException(400, "ts_from no puede ser mayor que ts_to")

def _validate_sort(sort: str, allowed: dict):
    if sort not in allowed:
        raise HTTPException(400, f"Parámetro sort inválido. Permitidos: {', '.join(allowed.keys())}")
    return allowed[sort]

def _validate_ingesta_payload(db: Session, p: IngestaCreate):
    # 1) asset y motor deben existir (si vienen)
    if p.asset_codigo:
        exists_asset = db.query(Asset).filter(Asset.asset_codigo == p.asset_codigo).first()
        if not exists_asset:
            raise HTTPException(400, "asset_codigo no existe")
    if p.motor_codigo:
        exists_motor = db.query(Motor).filter(Motor.motor_codigo == p.motor_codigo).first()
        if not exists_motor:
            raise HTTPException(400, "motor_codigo no existe")

    # 2) variable debe existir en catálogo
    if not p.variable:
        raise HTTPException(400, "variable es obligatoria")
    if not db.query(Variable).filter(Variable.nombre == p.variable).first():
        raise HTTPException(400, "variable no registrada en catálogo de variables")

    # Si hay regla de rango/tipo para la variable
    rule = VARIABLE_RULES.get(p.variable)
    if rule is not None:
        expected_type = rule.get("type", (int, float))
        if not isinstance(p.valor, expected_type):
            raise HTTPException(400, f"valor debe ser numérico para variable {p.variable}")
        vmin = rule.get("min", None)
        vmax = rule.get("max", None)
        if vmin is not None and p.valor < vmin:
            raise HTTPException(400, f"valor para {p.variable} menor que mínimo permitido ({vmin})")
        if vmax is not None and p.valor > vmax:
            raise HTTPException(400, f"valor para {p.variable} mayor que máximo permitido ({vmax})")

    # 3) ts_utc obligatorio, no futuro, no demasiado antiguo
    if not p.ts_utc:
        raise HTTPException(400, "ts_utc es obligatorio")
    now = _utc_now()
    if p.ts_utc > now + timedelta(seconds=5):
        raise HTTPException(400, "ts_utc no puede estar en el futuro")
    if p.ts_utc < now - timedelta(days=MAX_BACK_DAYS):
        raise HTTPException(400, f"ts_utc no puede ser anterior a {MAX_BACK_DAYS} días")

    # 4) anti-duplicados “cercanos” (misma asset/motor/variable en ±1s)
    dup = (
        db.query(Ingesta)
        .filter(
            (Ingesta.asset_codigo == p.asset_codigo) if p.asset_codigo else Ingesta.asset_codigo.is_(None),
            (Ingesta.motor_codigo == p.motor_codigo) if p.motor_codigo else Ingesta.motor_codigo.is_(None),
            Ingesta.variable == p.variable,
            Ingesta.ts_utc >= p.ts_utc - timedelta(seconds=1),
            Ingesta.ts_utc <= p.ts_utc + timedelta(seconds=1),
        )
        .first()
    )
    if dup:
        raise HTTPException(409, "Registro duplicado detectado (ventana de ±1s)")

# -------------------------
# Endpoints
# -------------------------

@router.get("/", response_model=List[IngestaRead])
def list_ingestas(
    asset_codigo: Optional[str] = Query(None),
    motor_codigo: Optional[str] = Query(None),
    variable: Optional[str] = Query(None),
    ts_from: Optional[datetime] = Query(None),
    ts_to: Optional[datetime] = Query(None),
    sort: str = Query("-ts_utc", description="Campo para ordenar. Ej: ts_utc o -ts_utc"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _validate_time_window(ts_from, ts_to)

    q = db.query(Ingesta)
    if asset_codigo:
        q = q.filter(Ingesta.asset_codigo == asset_codigo)
    if motor_codigo:
        q = q.filter(Ingesta.motor_codigo == motor_codigo)
    if variable:
        q = q.filter(Ingesta.variable == variable)
    if ts_from:
        q = q.filter(Ingesta.ts_utc >= ts_from)
    if ts_to:
        q = q.filter(Ingesta.ts_utc <= ts_to)

    sort_map = {
        "ts_utc": Ingesta.ts_utc,
        "-ts_utc": desc(Ingesta.ts_utc),
        "recibido_en": Ingesta.recibido_en,
        "-recibido_en": desc(Ingesta.recibido_en),
        "variable": Ingesta.variable,
        "-variable": desc(Ingesta.variable),
    }
    q = q.order_by(_validate_sort(sort, sort_map))

    return q.offset(offset).limit(_clamp_limit(limit)).all()

@router.get("/latest", response_model=List[IngestaRead])
def latest_ingestas(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
):
    return (
        db.query(Ingesta)
        .order_by(desc(Ingesta.ts_utc), desc(Ingesta.ingesta_id))
        .limit(_clamp_limit(limit))
        .all()
    )

@router.get("/last/{n}", response_model=List[IngestaRead])
def last_n_ingestas(n: int, db: Session = Depends(get_db)):
    return (
        db.query(Ingesta)
        .order_by(desc(Ingesta.ts_utc), desc(Ingesta.ingesta_id))
        .limit(_clamp_limit(n))
        .all()
    )

@router.get("/{ingesta_id}", response_model=IngestaRead)
def get_ingesta(ingesta_id: int, db: Session = Depends(get_db)):
    row = db.query(Ingesta).filter(Ingesta.ingesta_id == ingesta_id).first()
    if not row:
        raise HTTPException(404, "Ingesta no encontrada")
    return row

@router.post("/", response_model=IngestaRead, status_code=status.HTTP_201_CREATED)
def create_ingesta(payload: IngestaCreate, db: Session = Depends(get_db)):
    # Si el flujo MQTT→ingestas está activo, se bloquea la creación manual
    if getattr(settings, "MQTT_INGEST_ENABLED", False):
        raise HTTPException(403, "Ingesta manual deshabilitada (flujo MQTT activo)")

    _validate_ingesta_payload(db, payload)
    row = Ingesta(**payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.put("/{ingesta_id}", response_model=IngestaRead)
def update_ingesta(ingesta_id: int, payload: IngestaUpdate, db: Session = Depends(get_db)):
    row = db.query(Ingesta).filter(Ingesta.ingesta_id == ingesta_id).first()
    if not row:
        raise HTTPException(404, "Ingesta no encontrada")

    # Campos inmutables (sistema)
    immutable = {"ts_local_tz", "recibido_en", "ingesta_id"}
    for k in payload.dict(exclude_unset=True).keys():
        if k in immutable:
            raise HTTPException(400, f"No se permite modificar el campo inmutable: {k}")

    # Validar nuevamente con datos propuestos
    data = payload.dict(exclude_unset=True)
    create_like = IngestaCreate(
        asset_codigo=data.get("asset_codigo", row.asset_codigo),
        motor_codigo=data.get("motor_codigo", row.motor_codigo),
        ts_utc=data.get("ts_utc", row.ts_utc),
        variable=data.get("variable", row.variable),
        valor=data.get("valor", row.valor),
        archivo_origen=data.get("archivo_origen", row.archivo_origen),
    )
    _validate_ingesta_payload(db, create_like)

    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row

@router.delete("/{ingesta_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ingesta(ingesta_id: int, db: Session = Depends(get_db)):
    row = db.query(Ingesta).filter(Ingesta.ingesta_id == ingesta_id).first()
    if not row:
        raise HTTPException(404, "Ingesta no encontrada")
    # Solo permitir eliminar si es reciente (<24h)
    if (_utc_now() - row.ts_utc) > timedelta(hours=24):
        raise HTTPException(403, "No se puede eliminar una ingesta con más de 24 horas")
    db.delete(row)
    db.commit()
    return

@router.get("/export/csv")
def export_csv(
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    variable: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    _validate_time_window(ts_from, ts_to)

    q = db.query(Ingesta)
    if asset_codigo: q = q.filter(Ingesta.asset_codigo == asset_codigo)
    if motor_codigo: q = q.filter(Ingesta.motor_codigo == motor_codigo)
    if variable:     q = q.filter(Ingesta.variable == variable)
    if ts_from:      q = q.filter(Ingesta.ts_utc >= ts_from)
    if ts_to:        q = q.filter(Ingesta.ts_utc <= ts_to)

    q = q.order_by(asc(Ingesta.ts_utc)).limit(MAX_CSV_ROWS + 1)
    rows = q.all()
    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(413, f"Demasiadas filas para exportar (> {MAX_CSV_ROWS}). Aplique más filtros.")

    stream = io.StringIO()
    w = csv.writer(stream)
    # Nota: si su columna real es ts_local_tz, asegúrese de que el modelo la mapee correctamente.
    w.writerow(["ingesta_id","asset_codigo","motor_codigo","ts_utc","ts_local_tz","variable","valor","archivo_origen","recibido_en"])
    for r in rows:
        w.writerow([
            r.ingesta_id,
            r.asset_codigo,
            r.motor_codigo,
            r.ts_utc,
            getattr(r, "ts_local_tz", None),  # debe existir en el modelo (mapear a ts_local_tz si aplica)
            r.variable,
            r.valor,
            r.archivo_origen,
            r.recibido_en
        ])

    stream.seek(0)
    headers = {"Content-Disposition": "attachment; filename=ingestas.csv"}
    return StreamingResponse(stream, media_type="text/csv", headers=headers)
