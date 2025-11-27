from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, text
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from fastapi.responses import StreamingResponse
import io, csv

from ..database import get_db
from ..models.mediciones import Medicion
from ..models.despliegues import Despliegue
from ..models.assets import Asset
from ..models.motores import Motor
from ..models.variables import Variable
from ..schemas.mediciones import MedicionRead, MedicionCreate, MedicionUpdate
from ..config import settings
from ..mqtt_client import mqtt_client

from pydantic import BaseModel

# -------------------------------------------------------------------
# Modelos auxiliares para la importación desde ingestas
# -------------------------------------------------------------------

class ImportFromIngestasRequest(BaseModel):
    asset_codigo: Optional[str] = None
    motor_codigo: Optional[str] = None
    variable: Optional[str] = None
    ts_from: Optional[datetime] = None
    ts_to: Optional[datetime] = None
    indicador_calidad: int = 0


class ImportFromIngestasResponse(BaseModel):
    inserted: int


# -------------------------------------------------------------------
# Modelos para inserción masiva (bulk)
# -------------------------------------------------------------------

class BulkMedicionesRequest(BaseModel):
    """
    Request para inserción masiva de mediciones.
    items: lista de MedicionCreate (misma estructura que el POST normal).
    """
    items: List[MedicionCreate]


class BulkMedicionesResponse(BaseModel):
    inserted: int
    skipped: int


router = APIRouter()

# -------------------------------------------------------------------
# Reglas y constantes
# -------------------------------------------------------------------

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
        raise HTTPException(
            400,
            f"Parámetro sort inválido. Permitidos: {', '.join(allowed.keys())}"
        )
    return allowed[sort]


# -------------------------------------------------------------------
# Validación de payload (POST individual)
# -------------------------------------------------------------------

def _validate_medicion_payload(db: Session, p: MedicionCreate):
    # --- NORMALIZACIÓN DE TIMEZONE ---
    if p.ts_utc and p.ts_utc.tzinfo is None:
        p.ts_utc = p.ts_utc.replace(tzinfo=timezone.utc)

    d = db.query(Despliegue).filter(Despliegue.despliegue_id == p.despliegue_id).first()
    if not d:
        raise HTTPException(400, "despliegue_id no existe")

    # OJO: en tu modelo Variable, la PK se llama "variable"
    if not db.query(Variable).filter(Variable.variable == p.variable).first():
        raise HTTPException(400, "variable no registrada en catálogo de variables")

    if not p.ts_utc:
        raise HTTPException(400, "ts_utc es obligatorio")

    now = _utc_now()
    if p.ts_utc > now + timedelta(seconds=5):
        raise HTTPException(400, "ts_utc no puede estar en el futuro")

    # Si en el futuro quieres volver a activar estas reglas, solo descomentas:
    """
    if d.inicio and p.ts_utc < d.inicio:
        raise HTTPException(400, "ts_utc anterior al inicio del despliegue")
    if d.fin and p.ts_utc > d.fin:
        raise HTTPException(400, "ts_utc posterior al fin del despliegue")
    """

    # Esta condición deja la verificación de duplicados desactivada en la práctica
    dup = (
        db.query(Medicion)
        .filter(
            Medicion.despliegue_id == p.despliegue_id,
            Medicion.variable == p.variable,
            Medicion.ts_utc == p.ts_utc
        )
        .filter(Medicion.medicion_id != Medicion.medicion_id)  # siempre False
        .first()
    )

    if dup:
        raise HTTPException(409, "Medición duplicada")


# -------------------------------------------------------------------
# IMPORTACIÓN DESDE INGESTAS
# -------------------------------------------------------------------

@router.post("/import-from-ingestas", response_model=ImportFromIngestasResponse)
def import_mediciones_from_ingestas(
    payload: ImportFromIngestasRequest,
    db: Session = Depends(get_db),
):
    sql = text("""
        INSERT INTO iot.mediciones (
            despliegue_id, ts_utc, variable, valor,
            indicador_calidad
        )
        SELECT
            d.despliegue_id,
            i.ts_utc,
            i.variable,
            i.valor,
            :indicador_calidad
        FROM raw.ingestas i
        JOIN iot.assets a
          ON a.asset_codigo = i.asset_codigo
        JOIN iot.motores m
          ON m.motor_codigo = i.motor_codigo
        JOIN iot.despliegues d
          ON d.asset_id = a.asset_id
         AND d.motor_id = m.motor_id
         AND i.ts_utc >= d.inicio
         AND (d.fin IS NULL OR i.ts_utc <= d.fin)
        WHERE 1=1
          AND (:asset_codigo IS NULL OR i.asset_codigo = :asset_codigo)
          AND (:motor_codigo IS NULL OR i.motor_codigo = :motor_codigo)
          AND (:variable     IS NULL OR i.variable     = :variable)
          AND (:ts_from      IS NULL OR i.ts_utc >= :ts_from)
          AND (:ts_to        IS NULL OR i.ts_utc <= :ts_to)
        -- NOTA: para que ON CONFLICT funcione se necesita un índice único en BD
        --       por ejemplo: UNIQUE(despliegue_id, ts_utc, variable)
        ON CONFLICT (despliegue_id, ts_utc, variable) DO NOTHING;
    """)

    result = db.execute(sql, {
        "asset_codigo": payload.asset_codigo,
        "motor_codigo": payload.motor_codigo,
        "variable": payload.variable,
        "ts_from": payload.ts_from,
        "ts_to": payload.ts_to,
        "indicador_calidad": payload.indicador_calidad,
    })
    db.commit()

    return ImportFromIngestasResponse(inserted=(result.rowcount or 0))


# -------------------------------------------------------------------
# INSERCIÓN MASIVA (BULK) DESDE EL FRONTEND / CLIENTES
# -------------------------------------------------------------------

@router.post("/bulk", response_model=BulkMedicionesResponse,
             status_code=status.HTTP_201_CREATED)
def bulk_create_mediciones(
    payload: BulkMedicionesRequest,
    db: Session = Depends(get_db),
):
    """
    Inserta muchas mediciones en un solo request y un solo commit.

    - Recibe: { "items": [ MedicionCreate, MedicionCreate, ... ] }
    - Valida despliegue, variable y fecha.
    - Normaliza ts_utc a UTC si viene sin tz.
    - Inserta en bloque: db.add_all(...) + commit().
    """

    if READ_ONLY:
        raise HTTPException(403, "Escritura deshabilitada (ALLOW_WRITE_MEDICIONES=false)")

    if not payload.items:
        return BulkMedicionesResponse(inserted=0, skipped=0)

    now = _utc_now()

    # 1) Cargar despliegues y variables necesarios en memoria (una sola consulta por cada uno)
    despl_ids = {item.despliegue_id for item in payload.items if item.despliegue_id is not None}
    var_names = {item.variable for item in payload.items if item.variable is not None}

    despliegues = (
        db.query(Despliegue)
        .filter(Despliegue.despliegue_id.in_(despl_ids))
        .all()
    )
    despl_map = {d.despliegue_id: d for d in despliegues}

    variables = (
        db.query(Variable)
        .filter(Variable.variable.in_(var_names))
        .all()
    )
    var_set = {v.variable for v in variables}

    to_insert: List[Medicion] = []
    skipped = 0

    for item in payload.items:
        # Normalizar ts_utc
        ts = item.ts_utc
        if ts is None:
            skipped += 1
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Reglas básicas de tiempo
        if ts > now + timedelta(seconds=5):
            skipped += 1
            continue

        # Validar despliegue
        d = despl_map.get(item.despliegue_id)
        if not d:
            skipped += 1
            continue

        # Validar variable
        if item.variable not in var_set:
            skipped += 1
            continue

        # Si quisieras validar rango del despliegue, aquí sería el lugar:
        """
        if d.inicio and ts < d.inicio:
            skipped += 1
            continue
        if d.fin and ts > d.fin:
            skipped += 1
            continue
        """

        # Construir objeto Medicion listo para insertar
        m = Medicion(
            despliegue_id=item.despliegue_id,
            ts_utc=ts,
            variable=item.variable,
            valor=item.valor,
            # indicador_calidad: usa default de la BD (0) o agrega si lo tienes en el schema
        )
        to_insert.append(m)

    if to_insert:
        db.add_all(to_insert)
        db.commit()
        inserted = len(to_insert)
    else:
        inserted = 0

    return BulkMedicionesResponse(inserted=inserted, skipped=skipped)


# -------------------------------------------------------------------
# LECTURA: ahora TODA basada en ts_local_tz (coherencia local)
# -------------------------------------------------------------------

@router.get("/latest", response_model=List[MedicionRead])
def latest_mediciones(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
):
    q = (
        db.query(Medicion)
        .order_by(desc(Medicion.ts_local_tz), desc(Medicion.medicion_id))
        .limit(_clamp_limit(limit))
    )
    return q.all()


@router.get("/last/{n}", response_model=List[MedicionRead])
def last_n_mediciones(n: int, db: Session = Depends(get_db)):
    q = (
        db.query(Medicion)
        .order_by(desc(Medicion.ts_local_tz), desc(Medicion.medicion_id))
        .limit(_clamp_limit(n))
    )
    return q.all()


@router.get("/", response_model=List[MedicionRead])
def list_mediciones(
    asset_codigo: Optional[str] = Query(None),
    motor_codigo: Optional[str] = Query(None),
    variable: Optional[str] = Query(None),
    ts_from: Optional[datetime] = Query(None),
    ts_to: Optional[datetime] = Query(None),
    sort: str = Query("-ts_local_tz"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _validate_time_window(ts_from, ts_to)

    q = (
        db.query(Medicion)
        .join(Despliegue, Medicion.despliegue_id == Despliegue.despliegue_id)
        .join(Asset, Despliegue.asset_id == Asset.asset_id)
        .join(Motor, Despliegue.motor_id == Motor.motor_id)
    )

    if asset_codigo:
        q = q.filter(Asset.asset_codigo == asset_codigo)
    if motor_codigo:
        q = q.filter(Motor.motor_codigo == motor_codigo)
    if variable:
        q = q.filter(Medicion.variable == variable)
    if ts_from:
        q = q.filter(Medicion.ts_local_tz >= ts_from)
    if ts_to:
        q = q.filter(Medicion.ts_local_tz <= ts_to)

    sort_map = {
        "ts_utc": Medicion.ts_utc,
        "-ts_utc": desc(Medicion.ts_utc),
        "ts_local_tz": Medicion.ts_local_tz,
        "-ts_local_tz": desc(Medicion.ts_local_tz),
        "variable": Medicion.variable,
        "-variable": desc(Medicion.variable),
    }

    sort_col = _validate_sort(sort, sort_map)
    q = q.order_by(sort_col)

    return q.offset(offset).limit(_clamp_limit(limit)).all()


# -------------------------------------------------------------------
# EXPORTACIÓN CSV usando ts_local_tz
# -------------------------------------------------------------------

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

    q = (
        db.query(Medicion, Asset.asset_codigo, Motor.motor_codigo)
        .join(Despliegue, Medicion.despliegue_id == Despliegue.despliegue_id)
        .join(Asset, Despliegue.asset_id == Asset.asset_id)
        .join(Motor, Despliegue.motor_id == Motor.motor_id)
    )

    if asset_codigo:
        q = q.filter(Asset.asset_codigo == asset_codigo)
    if motor_codigo:
        q = q.filter(Motor.motor_codigo == motor_codigo)
    if variable:
        q = q.filter(Medicion.variable == variable)
    if ts_from:
        q = q.filter(Medicion.ts_local_tz >= ts_from)
    if ts_to:
        q = q.filter(Medicion.ts_local_tz <= ts_to)

    q = q.order_by(asc(Medicion.ts_local_tz)).limit(MAX_CSV_ROWS + 1)
    rows = q.all()

    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(413, "Demasiadas filas para exportar (> 50,000)")

    stream = io.StringIO()
    w = csv.writer(stream)
    w.writerow([
        "medicion_id", "asset_codigo", "motor_codigo",
        "ts_utc", "ts_local_tz",
        "variable", "valor", "importado_en"
    ])

    for m, a_code, m_code in rows:
        w.writerow([
            m.medicion_id,
            a_code,
            m_code,
            m.ts_utc,
            m.ts_local_tz,
            m.variable,
            m.valor,
            m.importado_en,
        ])

    stream.seek(0)
    headers = {"Content-Disposition": "attachment; filename=mediciones.csv"}
    return StreamingResponse(stream, media_type="text/csv", headers=headers)


# -------------------------------------------------------------------
# ESCRITURA (fila a fila)
# -------------------------------------------------------------------

@router.post("/", response_model=MedicionRead, status_code=status.HTTP_201_CREATED)
def create_medicion(payload: MedicionCreate, db: Session = Depends(get_db)):
    if READ_ONLY:
        raise HTTPException(403, "Escritura deshabilitada (ALLOW_WRITE_MEDICIONES=false)")

    _validate_medicion_payload(db, payload)

    m = Medicion(**payload.dict())
    db.add(m)
    db.commit()
    db.refresh(m)

    d = db.query(Despliegue).filter(Despliegue.despliegue_id == m.despliegue_id).first()
    a = db.query(Asset).filter(Asset.asset_id == d.asset_id).first() if d else None
    mo = db.query(Motor).filter(Motor.motor_id == d.motor_id).first() if d else None

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
        "medicion_id": m.medicion_id,
        "despliegue_id": m.despliegue_id,
        "ts_utc": m.ts_utc,
        "ts_local_tz": m.ts_local_tz,
        "variable": m.variable,
        "valor": m.valor,
        "importado_en": m.importado_en,
        "asset_codigo": a.asset_codigo if a else None,
        "motor_codigo": mo.motor_codigo if mo else None,
    }


@router.put("/{medicion_id}", response_model=MedicionRead)
def update_medicion(medicion_id: int, payload: MedicionUpdate, db: Session = Depends(get_db)):
    if READ_ONLY:
        raise HTTPException(403, "Escritura deshabilitada (ALLOW_WRITE_MEDICIONES=false)")

    m = db.query(Medicion).filter(Medicion.medicion_id == medicion_id).first()
    if not m:
        raise HTTPException(404, "Medición no encontrada")

    immutable = {"ts_local_tz", "importado_en", "medicion_id"}
    for k in payload.dict(exclude_unset=True).keys():
        if k in immutable:
            raise HTTPException(400, f"No se permite modificar el campo inmutable: {k}")

    data = payload.dict(exclude_unset=True)

    create_like = MedicionCreate(
        despliegue_id=data.get("despliegue_id", m.despliegue_id),
        ts_utc=data.get("ts_utc", m.ts_utc),
        variable=data.get("variable", m.variable),
        valor=data.get("valor", m.valor),
    )
    _validate_medicion_payload(db, create_like)

    for k, v in data.items():
        setattr(m, k, v)

    db.commit()
    db.refresh(m)

    d = db.query(Despliegue).filter(Despliegue.despliegue_id == m.despliegue_id).first()
    a = db.query(Asset).filter(Asset.asset_id == d.asset_id).first() if d else None
    mo = db.query(Motor).filter(Motor.motor_id == d.motor_id).first() if d else None

    return {
        "medicion_id": m.medicion_id,
        "despliegue_id": m.despliegue_id,
        "ts_utc": m.ts_utc,
        "ts_local_tz": m.ts_local_tz,
        "variable": m.variable,
        "valor": m.valor,        
        "importado_en": m.importado_en,
        "asset_codigo": a.asset_codigo if a else None,
        "motor_codigo": mo.motor_codigo if mo else None,
    }


@router.delete("/{medicion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medicion(medicion_id: int, db: Session = Depends(get_db)):
    if READ_ONLY:
        raise HTTPException(403, "Escritura deshabilitada (ALLOW_WRITE_MEDICIONES=false)")

    m = db.query(Medicion).filter(Medicion.medicion_id == medicion_id).first()

    if not m:
        raise HTTPException(404, "Medición no encontrada")

    db.delete(m)
    db.commit()
    return
