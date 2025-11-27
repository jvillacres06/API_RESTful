# app/routers/caracteristicas.py

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import List, Optional
from datetime import datetime, timezone
from fastapi.responses import StreamingResponse
import io, csv

from ..database import get_db
from ..models.caracteristicas import Caracteristica
from ..models.despliegues import Despliegue
from ..models.assets import Asset
from ..models.motores import Motor
from ..schemas.caracteristicas import (
    CaracteristicaRead,
    CaracteristicaCreate,
    CaracteristicaUpdate,
)

from pydantic import BaseModel

router = APIRouter()

# Límites de negocio
MAX_LIMIT = 1000
DEFAULT_LIMIT = 100
MAX_CSV_ROWS = 50_000


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


# ============================================================
# MODELOS PARA INSERCIÓN MASIVA (BULK)
# ============================================================

class BulkCaracteristicasRequest(BaseModel):
    """
    Inserción masiva de características.
    items: lista de CaracteristicaCreate (misma estructura que el POST normal).
    """
    items: List[CaracteristicaCreate]


class BulkCaracteristicasResponse(BaseModel):
    inserted: int
    skipped: int


# ============================================================
# LISTADOS (TODO usando ts_local_tz)
# ============================================================

@router.get("/", response_model=List[CaracteristicaRead])
def list_caracteristicas(
    asset_codigo: Optional[str] = Query(None),
    motor_codigo: Optional[str] = Query(None),
    variable: Optional[str] = Query(None),
    caracteristica: Optional[str] = Query(None),
    ventana_s: Optional[int] = Query(None),
    indicador_calidad: Optional[int] = Query(None),
    ts_from: Optional[datetime] = Query(None),
    ts_to: Optional[datetime] = Query(None),
    sort: str = Query(
        "-ts_local_tz",
        description="Ej: ts_local_tz, -ts_local_tz, variable, -variable"
    ),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Listado de características usando hora local (ts_local_tz).
    """

    q = (
        db.query(Caracteristica)
        .join(Despliegue, Caracteristica.despliegue_id == Despliegue.despliegue_id)
        .join(Asset, Despliegue.asset_id == Asset.asset_id)
        .join(Motor, Despliegue.motor_id == Motor.motor_id)
    )

    # Filtros
    if asset_codigo:
        q = q.filter(Asset.asset_codigo == asset_codigo)
    if motor_codigo:
        q = q.filter(Motor.motor_codigo == motor_codigo)
    if variable:
        q = q.filter(Caracteristica.variable == variable)
    if caracteristica:
        q = q.filter(Caracteristica.caracteristica == caracteristica)
    if ventana_s is not None:
        q = q.filter(Caracteristica.ventana_s == ventana_s)
    if indicador_calidad is not None:
        q = q.filter(Caracteristica.indicador_calidad == indicador_calidad)

    # FILTRO TEMPORAL - AHORA por ts_local_tz
    if ts_from:
        q = q.filter(Caracteristica.ts_local_tz >= ts_from)
    if ts_to:
        q = q.filter(Caracteristica.ts_local_tz <= ts_to)

    # Orden
    sort_map = {
        "ts_utc": Caracteristica.ts_utc,
        "-ts_utc": desc(Caracteristica.ts_utc),
        "ts_local_tz": Caracteristica.ts_local_tz,
        "-ts_local_tz": desc(Caracteristica.ts_local_tz),
        "variable": Caracteristica.variable,
        "-variable": desc(Caracteristica.variable),
        "caracteristica": Caracteristica.caracteristica,
        "-caracteristica": desc(Caracteristica.caracteristica),
    }

    sort_col = sort_map.get(sort, desc(Caracteristica.ts_local_tz))
    q = q.order_by(sort_col)

    return q.offset(offset).limit(_clamp_limit(limit)).all()


@router.get("/latest", response_model=List[CaracteristicaRead])
def latest_caracteristicas(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
):
    return (
        db.query(Caracteristica)
        .order_by(desc(Caracteristica.ts_local_tz), desc(Caracteristica.caracteristica_id))
        .limit(_clamp_limit(limit))
        .all()
    )


@router.get("/last/{n}", response_model=List[CaracteristicaRead])
def last_n_caracteristicas(
    n: int,
    db: Session = Depends(get_db),
):
    return (
        db.query(Caracteristica)
        .order_by(desc(Caracteristica.ts_local_tz), desc(Caracteristica.caracteristica_id))
        .limit(_clamp_limit(n))
        .all()
    )


# ============================================================
# EXPORTACIÓN CSV USANDO ts_local_tz
# ============================================================

@router.get("/export/csv")
def export_caracteristicas_csv(
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    variable: Optional[str] = None,
    caracteristica: Optional[str] = None,
    ventana_s: Optional[int] = None,
    indicador_calidad: Optional[int] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(Caracteristica, Asset.asset_codigo, Motor.motor_codigo)
        .join(Despliegue, Caracteristica.despliegue_id == Despliegue.despliegue_id)
        .join(Asset, Despliegue.asset_id == Asset.asset_id)
        .join(Motor, Despliegue.motor_id == Motor.motor_id)
    )

    # filtros
    if asset_codigo: q = q.filter(Asset.asset_codigo == asset_codigo)
    if motor_codigo: q = q.filter(Motor.motor_codigo == motor_codigo)
    if variable: q = q.filter(Caracteristica.variable == variable)
    if caracteristica: q = q.filter(Caracteristica.caracteristica == caracteristica)
    if ventana_s is not None: q = q.filter(Caracteristica.ventana_s == ventana_s)
    if indicador_calidad is not None: q = q.filter(Caracteristica.indicador_calidad == indicador_calidad)

    # filtro temporal por ts_local_tz
    if ts_from: q = q.filter(Caracteristica.ts_local_tz >= ts_from)
    if ts_to: q = q.filter(Caracteristica.ts_local_tz <= ts_to)

    q = q.order_by(asc(Caracteristica.ts_local_tz)).limit(MAX_CSV_ROWS + 1)
    rows = q.all()

    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(413, f"Demasiadas filas (> {MAX_CSV_ROWS})")

    stream = io.StringIO()
    w = csv.writer(stream)
    w.writerow([
        "caracteristica_id",
        "asset_codigo",
        "motor_codigo",
        "despliegue_id",
        "ts_utc",
        "ts_local_tz",
        "variable",
        "caracteristica",
        "valor",
        "ventana_s",
        "indicador_calidad",
        "generado_en",
    ])

    for c, a_code, m_code in rows:
        w.writerow([
            c.caracteristica_id,
            a_code,
            m_code,
            c.despliegue_id,
            c.ts_utc,
            c.ts_local_tz,
            c.variable,
            c.caracteristica,
            c.valor,
            c.ventana_s,
            c.indicador_calidad,
            c.generado_en,
        ])

    stream.seek(0)
    headers = {"Content-Disposition": "attachment; filename=caracteristicas.csv"}
    return StreamingResponse(stream, media_type="text/csv", headers=headers)


# ============================================================
# INSERCIÓN MASIVA (BULK)
# ============================================================

@router.post("/bulk", response_model=BulkCaracteristicasResponse,
             status_code=status.HTTP_201_CREATED)
def bulk_create_caracteristicas(
    payload: BulkCaracteristicasRequest,
    db: Session = Depends(get_db),
):
    """
    Inserta muchas características en un solo request y un solo commit.

    - Recibe: { "items": [ CaracteristicaCreate, ... ] }
    - Normaliza ts_utc a UTC si viene sin timezone.
    - Valida que el despliegue exista.
    """

    if not payload.items:
        return BulkCaracteristicasResponse(inserted=0, skipped=0)

    # Cargar despliegues necesarios en memoria
    despl_ids = {item.despliegue_id for item in payload.items if item.despliegue_id is not None}
    if despl_ids:
        despliegues = (
            db.query(Despliegue)
            .filter(Despliegue.despliegue_id.in_(despl_ids))
            .all()
        )
        despl_map = {d.despliegue_id: d for d in despliegues}
    else:
        despl_map = {}

    to_insert: List[Caracteristica] = []
    skipped = 0

    for item in payload.items:
        # Validar despliegue
        if item.despliegue_id is None or item.despliegue_id not in despl_map:
            skipped += 1
            continue

        # Normalizar ts_utc
        ts = item.ts_utc
        if ts is None:
            skipped += 1
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Construir objeto Caracteristica
        c = Caracteristica(
            despliegue_id=item.despliegue_id,
            ts_utc=ts,
            variable=item.variable,
            caracteristica=item.caracteristica,
            valor=item.valor,
            ventana_s=item.ventana_s,
            indicador_calidad=item.indicador_calidad,
        )
        to_insert.append(c)

    if to_insert:
        db.add_all(to_insert)
        db.commit()
        inserted = len(to_insert)
    else:
        inserted = 0

    return BulkCaracteristicasResponse(inserted=inserted, skipped=skipped)


# ============================================================
# CRUD
# ============================================================

@router.get("/{caracteristica_id}", response_model=CaracteristicaRead)
def get_caracteristica(
    caracteristica_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(Caracteristica)
        .filter(Caracteristica.caracteristica_id == caracteristica_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Característica no encontrada")
    return row


@router.post("/", response_model=CaracteristicaRead, status_code=status.HTTP_201_CREATED)
def create_caracteristica(
    payload: CaracteristicaCreate,
    db: Session = Depends(get_db),
):
    row = Caracteristica(**payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{caracteristica_id}", response_model=CaracteristicaRead)
def update_caracteristica(
    caracteristica_id: int,
    payload: CaracteristicaUpdate,
    db: Session = Depends(get_db),
):
    row = (
        db.query(Caracteristica)
        .filter(Caracteristica.caracteristica_id == caracteristica_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Característica no encontrada")

    for k, v in payload.dict(exclude_unset=True).items():
        setattr(row, k, v)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{caracteristica_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_caracteristica(
    caracteristica_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(Caracteristica)
        .filter(Caracteristica.caracteristica_id == caracteristica_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Característica no encontrada")

    db.delete(row)
    db.commit()
    return
