# app/routers/caracteristicas.py

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import List, Optional
from datetime import datetime
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

router = APIRouter()

# Límites de negocio para listados/export
MAX_LIMIT = 1000
DEFAULT_LIMIT = 100
MAX_CSV_ROWS = 50_000


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


# ==========================
# LISTADOS
# ==========================

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
        "-ts_utc",
        description="Campo para ordenar. Ej: ts_utc, -ts_utc, variable, -variable, caracteristica, -caracteristica",
    ),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Listado de características con filtros por:
    - asset_codigo, motor_codigo (via JOIN despliegues/assets/motores)
    - variable, caracteristica, ventana_s, indicador_calidad
    - rango de fechas ts_from / ts_to
    """
    q = (
        db.query(Caracteristica)
        .join(Despliegue, Caracteristica.despliegue_id == Despliegue.despliegue_id)
        .join(Asset, Despliegue.asset_id == Asset.asset_id)
        .join(Motor, Despliegue.motor_id == Motor.motor_id)
    )

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
    if ts_from:
        q = q.filter(Caracteristica.ts_utc >= ts_from)
    if ts_to:
        q = q.filter(Caracteristica.ts_utc <= ts_to)

    sort_map = {
        "ts_utc": Caracteristica.ts_utc,
        "-ts_utc": desc(Caracteristica.ts_utc),
        "variable": Caracteristica.variable,
        "-variable": desc(Caracteristica.variable),
        "caracteristica": Caracteristica.caracteristica,
        "-caracteristica": desc(Caracteristica.caracteristica),
        "ventana_s": Caracteristica.ventana_s,
        "-ventana_s": desc(Caracteristica.ventana_s),
        "indicador_calidad": Caracteristica.indicador_calidad,
        "-indicador_calidad": desc(Caracteristica.indicador_calidad),
    }
    sort_col = sort_map.get(sort, desc(Caracteristica.ts_utc))
    q = q.order_by(sort_col)

    return q.offset(offset).limit(_clamp_limit(limit)).all()


@router.get("/latest", response_model=List[CaracteristicaRead])
def latest_caracteristicas(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
):
    """
    Últimas N características (ordenadas por ts_utc, caracteristica_id desc)
    """
    return (
        db.query(Caracteristica)
        .order_by(desc(Caracteristica.ts_utc), desc(Caracteristica.caracteristica_id))
        .limit(_clamp_limit(limit))
        .all()
    )


@router.get("/last/{n}", response_model=List[CaracteristicaRead])
def last_n_caracteristicas(
    n: int,
    db: Session = Depends(get_db),
):
    """
    Últimas N características (path param).
    """
    return (
        db.query(Caracteristica)
        .order_by(desc(Caracteristica.ts_utc), desc(Caracteristica.caracteristica_id))
        .limit(_clamp_limit(n))
        .all()
    )


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
    """
    Exportar características a CSV con filtros.
    Incluye asset_codigo y motor_codigo en el archivo.
    """
    q = (
        db.query(
            Caracteristica,
            Asset.asset_codigo,
            Motor.motor_codigo,
        )
        .join(Despliegue, Caracteristica.despliegue_id == Despliegue.despliegue_id)
        .join(Asset, Despliegue.asset_id == Asset.asset_id)
        .join(Motor, Despliegue.motor_id == Motor.motor_id)
    )

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
    if ts_from:
        q = q.filter(Caracteristica.ts_utc >= ts_from)
    if ts_to:
        q = q.filter(Caracteristica.ts_utc <= ts_to)

    q = q.order_by(asc(Caracteristica.ts_utc)).limit(MAX_CSV_ROWS + 1)
    rows = q.all()
    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Demasiadas filas para exportar (> {MAX_CSV_ROWS}). Aplique más filtros.",
        )

    stream = io.StringIO()
    w = csv.writer(stream)
    w.writerow(
        [
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
        ]
    )

    for c, a_code, m_code in rows:
        w.writerow(
            [
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
            ]
        )

    stream.seek(0)
    headers = {"Content-Disposition": "attachment; filename=caracteristicas.csv"}
    return StreamingResponse(stream, media_type="text/csv", headers=headers)


# ==========================
# CRUD BÁSICO
# ==========================

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
