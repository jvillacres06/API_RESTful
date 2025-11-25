# app/routers/analytics_caracteristicas.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, text, asc, desc
from typing import Iterable, List, Optional
from datetime import datetime
import csv
import io

from ..database import get_db
from ..models.caracteristicas import Caracteristica
from ..models.despliegues import Despliegue
from ..models.assets import Asset
from ..models.motores import Motor

from ..schemas.analytics_caracteristicas import (
    BaseFiltrosCaracteristicas,
    CaracTrendRequest, CaracTrendResponse, CaracSeries, CaracPoint,
    CaracScatterRequest, CaracScatterResponse, CaracScatterPoint,
    CaracHistogramRequest, CaracHistogramResponse, CaracHistogramBucket,
    CaracAvailableVariablesResponse, CaracAvailableCaracteristicasResponse,
)

router = APIRouter()

# -------------------------------------
# Límites del sistema
# -------------------------------------
MAX_TREND_POINTS = 10_000
MAX_SCATTER_POINTS = 10_000
MAX_HIST_BINS = 200
MAX_EXPORT_ROWS = 200_000


def _clamp_limit(limit: int, max_limit: int) -> int:
    return max(1, min(limit, max_limit))


def _validate_time_window(ts_from: Optional[datetime], ts_to: Optional[datetime]):
    if ts_from and ts_to and ts_from > ts_to:
        raise HTTPException(400, "ts_from no puede ser mayor que ts_to")


# ============================================================
# Helper principal → APLICAR FILTROS usando ts_local_tz
# ============================================================
def _apply_filters(q, req: BaseFiltrosCaracteristicas, db: Session):
    conds = []

    # --------------- FILTRO POR FECHAS EN HORA LOCAL ---------------
    if getattr(req, "ts_from", None) is not None:
        conds.append(Caracteristica.ts_local_tz >= req.ts_from)

    if getattr(req, "ts_to", None) is not None:
        conds.append(Caracteristica.ts_local_tz <= req.ts_to)

    # --------------- FILTRO POR DESPLIEGUE DIRECTO ----------------
    if getattr(req, "despliegue_id", None):
        conds.append(Caracteristica.despliegue_id == req.despliegue_id)
        return q.where(and_(*conds))

    # --------------- Si filtra asset o motor → JOIN ---------------
    join_needed = (getattr(req, "asset_codigo", None) is not None) or \
                  (getattr(req, "motor_codigo", None) is not None)

    if join_needed:
        q = (
            q.join(Despliegue, Despliegue.despliegue_id == Caracteristica.despliegue_id)
             .join(Asset, Asset.asset_id == Despliegue.asset_id)
             .join(Motor, Motor.motor_id == Despliegue.motor_id)
        )

        if getattr(req, "asset_codigo", None):
            conds.append(Asset.asset_codigo == req.asset_codigo)

        if getattr(req, "motor_codigo", None):
            conds.append(Motor.motor_codigo == req.motor_codigo)

    if conds:
        q = q.where(and_(*conds))

    return q


# ============================================================
# Trend (Series de tiempo)
# ============================================================

@router.post("/caracteristicas/trend", response_model=CaracTrendResponse)
def carac_trend(req: CaracTrendRequest, db: Session = Depends(get_db)):

    if not req.variables:
        raise HTTPException(400, "Debe especificar variables")
    if not req.caracteristicas:
        raise HTTPException(400, "Debe especificar características")

    _validate_time_window(req.ts_from, req.ts_to)

    limit = _clamp_limit(req.limit, MAX_TREND_POINTS)

    series_out = []

    for var in req.variables:
        for car in req.caracteristicas:

            q = select(
                Caracteristica.ts_local_tz,
                Caracteristica.valor
            ).where(
                and_(
                    Caracteristica.variable == var,
                    Caracteristica.caracteristica == car
                )
            )

            q = _apply_filters(q, req, db).order_by(Caracteristica.ts_local_tz.asc()).limit(limit)

            rows = db.execute(q).all()

            points = [
                CaracPoint(ts_local_tz=r[0], valor=float(r[1]) if r[1] is not None else None)
                for r in rows
            ]

            series_out.append(
                CaracSeries(
                    variable=var,
                    caracteristica=car,
                    nombre=f"{var}:{car}",
                    points=points,
                )
            )

    return CaracTrendResponse(series=series_out)


# ============================================================
# Scatter
# ============================================================

@router.post("/caracteristicas/scatter", response_model=CaracScatterResponse)
def carac_scatter(req: CaracScatterRequest, db: Session = Depends(get_db)):

    if not req.variable:
        raise HTTPException(400, "Debe enviar una variable")
    if not req.caracteristica_x or not req.caracteristica_y:
        raise HTTPException(400, "Debe enviar caracteristica_x y caracteristica_y")

    _validate_time_window(req.ts_from, req.ts_to)
    limit = _clamp_limit(req.limit, MAX_SCATTER_POINTS)

    # Tabla base
    base = select(
        Caracteristica.despliegue_id,
        Caracteristica.variable,
        Caracteristica.caracteristica,
        Caracteristica.valor,
        Caracteristica.ts_local_tz
    ).where(Caracteristica.variable == req.variable)

    base = _apply_filters(base, req, db).subquery("base")

    tcol = base.c.ts_local_tz.label("bucket_ts")

    a = select(
        base.c.despliegue_id.label("d1"),
        tcol,
        base.c.valor.label("x")
    ).where(base.c.caracteristica == req.caracteristica_x).subquery("a")

    b = select(
        base.c.despliegue_id.label("d2"),
        tcol,
        base.c.valor.label("y")
    ).where(base.c.caracteristica == req.caracteristica_y).subquery("b")

    j = select(a.c.bucket_ts, a.c.x, b.c.y).where(
        and_(a.c.d1 == b.c.d2, a.c.bucket_ts == b.c.bucket_ts)
    ).order_by(a.c.bucket_ts.asc()).limit(limit)

    rows = db.execute(j).all()

    points = [
        CaracScatterPoint(
            ts_local_tz=r[0],
            x=float(r[1]) if r[1] is not None else None,
            y=float(r[2]) if r[2] is not None else None
        )
        for r in rows
    ]

    return CaracScatterResponse(
        variable=req.variable,
        x_caracteristica=req.caracteristica_x,
        y_caracteristica=req.caracteristica_y,
        points=points
    )


# ============================================================
# Histogram
# ============================================================

@router.post("/caracteristicas/histogram", response_model=CaracHistogramResponse)
def carac_histogram(req: CaracHistogramRequest, db: Session = Depends(get_db)):

    if req.bins < 1 or req.bins > MAX_HIST_BINS:
        raise HTTPException(400, f"bins debe estar entre 1 y {MAX_HIST_BINS}")

    _validate_time_window(req.ts_from, req.ts_to)

    # Rango min/max en hora local
    q_mm = select(
        func.min(Caracteristica.valor),
        func.max(Caracteristica.valor)
    ).where(
        and_(
            Caracteristica.variable == req.variable,
            Caracteristica.caracteristica == req.caracteristica
        )
    )

    q_mm = _apply_filters(q_mm, req, db)
    vmin, vmax = db.execute(q_mm).one()

    if vmin is None or vmax is None:
        return CaracHistogramResponse(
            variable=req.variable,
            caracteristica=req.caracteristica,
            min=None,
            max=None,
            bins=req.bins,
            buckets=[]
        )

    if vmin == vmax:
        return CaracHistogramResponse(
            variable=req.variable,
            caracteristica=req.caracteristica,
            min=float(vmin),
            max=float(vmax),
            bins=1,
            buckets=[CaracHistogramBucket(bucket=1, low=float(vmin), high=float(vmax), count=0)]
        )

    width = (vmax - vmin) / req.bins

    sql = text("""
        SELECT
          width_bucket(c.valor, :vmin, :vmax, :bins) AS b,
          MIN(c.valor) AS low,
          MAX(c.valor) AS high,
          COUNT(*)     AS cnt
        FROM iot.caracteristicas c
        JOIN iot.despliegues d ON d.despliegue_id = c.despliegue_id
        JOIN iot.assets a      ON a.asset_id      = d.asset_id
        JOIN iot.motores mo    ON mo.motor_id     = d.motor_id
        WHERE c.variable = :var
          AND c.caracteristica = :car
          AND (:from_ts IS NULL OR c.ts_local_tz >= :from_ts)
          AND (:to_ts   IS NULL OR c.ts_local_tz <= :to_ts)
          AND (:despliegue_id IS NULL OR c.despliegue_id = :despliegue_id)
          AND (:asset_codigo  IS NULL OR a.asset_codigo = :asset_codigo)
          AND (:motor_codigo  IS NULL OR mo.motor_codigo = :motor_codigo)
        GROUP BY b
        ORDER BY b
    """)

    rows = db.execute(sql, {
        "vmin": vmin,
        "vmax": vmax,
        "bins": req.bins,
        "var": req.variable,
        "car": req.caracteristica,
        "from_ts": req.ts_from,
        "to_ts": req.ts_to,
        "despliegue_id": req.despliegue_id,
        "asset_codigo": req.asset_codigo,
        "motor_codigo": req.motor_codigo,
    }).all()

    buckets = [
        CaracHistogramBucket(
            bucket=int(r.b),
            low=float(r.low),
            high=float(r.high),
            count=int(r.cnt)
        )
        for r in rows
    ]

    return CaracHistogramResponse(
        variable=req.variable,
        caracteristica=req.caracteristica,
        min=float(vmin),
        max=float(vmax),
        bins=req.bins,
        buckets=buckets
    )


# ============================================================
# Available Variables
# ============================================================

@router.get("/caracteristicas/available-variables",
            response_model=CaracAvailableVariablesResponse)
def carac_available_variables(
    despliegue_id: Optional[int] = None,
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    _validate_time_window(ts_from, ts_to)

    class R: pass

    req = R()
    req.despliegue_id = despliegue_id
    req.asset_codigo = asset_codigo
    req.motor_codigo = motor_codigo
    req.ts_from = ts_from
    req.ts_to = ts_to

    q = select(Caracteristica.variable).distinct()
    q = _apply_filters(q, req, db).order_by(Caracteristica.variable.asc())

    variables = [r[0] for r in db.execute(q).all()]

    return CaracAvailableVariablesResponse(variables=variables)


# ============================================================
# Available Características
# ============================================================

@router.get("/caracteristicas/available-caracteristicas",
            response_model=CaracAvailableCaracteristicasResponse)
def carac_available_caracteristicas(
    despliegue_id: Optional[int] = None,
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    _validate_time_window(ts_from, ts_to)

    class R: pass

    req = R()
    req.despliegue_id = despliegue_id
    req.asset_codigo = asset_codigo
    req.motor_codigo = motor_codigo
    req.ts_from = ts_from
    req.ts_to = ts_to

    q = select(Caracteristica.caracteristica).distinct()
    q = _apply_filters(q, req, db).order_by(Caracteristica.caracteristica.asc())

    características = [r[0] for r in db.execute(q).all()]

    return CaracAvailableCaracteristicasResponse(caracteristicas=características)


# ============================================================
# Export CSV (solo ts_local_tz)
# ============================================================

@router.get("/caracteristicas/export-csv")
def carac_export_csv(
    variables: List[str],
    caracteristicas: Optional[List[str]] = None,
    despliegue_id: Optional[int] = None,
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    limit: int = 200_000,
    db: Session = Depends(get_db)
):

    if not variables:
        raise HTTPException(400, "Debe especificar variables")

    _validate_time_window(ts_from, ts_to)
    limit = _clamp_limit(limit, MAX_EXPORT_ROWS)

    class R: pass

    req = R()
    req.despliegue_id = despliegue_id
    req.asset_codigo = asset_codigo
    req.motor_codigo = motor_codigo
    req.ts_from = ts_from
    req.ts_to = ts_to

    q = select(
        Caracteristica.ts_local_tz,
        Caracteristica.variable,
        Caracteristica.caracteristica,
        Caracteristica.valor,
        Caracteristica.despliegue_id,
    ).where(Caracteristica.variable.in_(variables))

    if caracteristicas:
        q = q.where(Caracteristica.caracteristica.in_(caracteristicas))

    q = _apply_filters(q, req, db).order_by(Caracteristica.ts_local_tz.asc()).limit(limit)

    rows = db.execute(q).all()

    def _gen():
        buf = io.StringIO()
        w = csv.writer(buf)

        w.writerow(["ts_local_tz", "variable", "caracteristica", "valor", "despliegue_id"])
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)

        for r in rows:
            w.writerow([r.ts_local_tz, r.variable, r.caracteristica, r.valor, r.despliegue_id])
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        _gen(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=caracteristicas.csv"}
    )
