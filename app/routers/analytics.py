# app/routers/analytics.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, text
from typing import Iterable, List, Optional
from datetime import datetime
import csv
import io

from ..database import get_db
from ..models.mediciones import Medicion
from ..models.despliegues import Despliegue
from ..models.assets import Asset
from ..models.motores import Motor

from ..schemas.analytics import (
    TrendRequest, TrendResponse, Series, Point,
    ScatterRequest, ScatterResponse, ScatterPoint,
    HistogramRequest, HistogramResponse, HistogramBucket,
    AvailableVariablesResponse,
)

router = APIRouter()

# -------------------------------
# Reglas de negocio
# -------------------------------

MAX_TREND_POINTS = 10_000
MAX_SCATTER_POINTS = 10_000
MAX_HIST_BINS = 200
MAX_EXPORT_ROWS = 200_000
MAX_VARIABLES_TREND = 10


def _clamp_limit(limit: int, max_limit: int) -> int:
    return max(1, min(limit, max_limit))


def _validate_time_window(ts_from: Optional[datetime], ts_to: Optional[datetime]):
    if ts_from and ts_to and ts_from > ts_to:
        raise HTTPException(400, "ts_from no puede ser mayor que ts_to")


# ======================
#  FILTROS (HORA LOCAL)
# ======================

def _apply_filters(q, req, db: Session):
    """
    Filtra SIEMPRE usando ts_local_tz (hora local) y,
    adicionalmente, por despliegue, asset, motor e indicador_calidad.
    """
    conds = []

    # 1) Rango temporal en hora local
    if getattr(req, "ts_from", None) is not None:
        conds.append(Medicion.ts_local_tz >= req.ts_from)

    if getattr(req, "ts_to", None) is not None:
        conds.append(Medicion.ts_local_tz <= req.ts_to)

    # 2) Filtro por calidad (lista o valor único)
    cal_list = getattr(req, "indicadores_calidad", None)
    if cal_list:
        conds.append(Medicion.indicador_calidad.in_(cal_list))
    else:
        cal_one = getattr(req, "indicador_calidad", None)
        if cal_one is not None:
            conds.append(Medicion.indicador_calidad == cal_one)

    # 3) Si se filtra directamente por despliegue
    if getattr(req, "despliegue_id", None):
        conds.append(Medicion.despliegue_id == req.despliegue_id)
        return q.where(and_(*conds))

    # 4) JOIN si se filtra por asset o motor
    join_needed = (getattr(req, "asset_codigo", None) is not None) or \
                  (getattr(req, "motor_codigo", None) is not None)

    if join_needed:
        q = (
            q.join(Despliegue, Despliegue.despliegue_id == Medicion.despliegue_id)
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


def _date_bucket(ts_col, align: str):
    """
    Para SCATTER: aplica date_trunc sobre ts_local_tz según align.
    """
    if align == "minute":
        return func.date_trunc("minute", ts_col)
    if align == "hour":
        return func.date_trunc("hour", ts_col)
    return ts_col


# ================================
#  ANALYTICS: TREND
# ================================

@router.post("/analytics/trend", response_model=TrendResponse)
def trend(req: TrendRequest, db: Session = Depends(get_db)):
    if not req.variables:
        raise HTTPException(400, "Debe especificar al menos una variable")

    if len(req.variables) > MAX_VARIABLES_TREND:
        raise HTTPException(400, f"Máximo {MAX_VARIABLES_TREND} variables permitidas")

    _validate_time_window(req.ts_from, req.ts_to)
    limit = _clamp_limit(req.limit, MAX_TREND_POINTS)

    out: List[Series] = []

    for var in req.variables:
        q = select(Medicion.ts_local_tz, Medicion.valor).where(Medicion.variable == var)
        q = _apply_filters(q, req, db).order_by(Medicion.ts_local_tz.asc()).limit(limit)

        rows = db.execute(q).all()

        # -----------------------------------------
        # ADAPTACIÓN PARA RANGOS LARGOS (ej. 1 mes)
        # -----------------------------------------
        if req.ts_from and req.ts_to:
            span_days = (req.ts_to - req.ts_from).total_seconds() / 86400.0
            # Regla simple: si el rango es >= 30 días,
            # hacemos downsampling 2:1 (15 min -> ~30 min)
            if span_days >= 30 and len(rows) > 1:
                rows = rows[::2]  # nos quedamos con 1 de cada 2 puntos

        points = [
            Point(ts_utc=r[0], valor=float(r[1]) if r[1] is not None else None)
            for r in rows
        ]

        out.append(Series(variable=var, points=points))

    return TrendResponse(series=out)


# ================================
#  ANALYTICS: SCATTER
# ================================

@router.post("/analytics/scatter", response_model=ScatterResponse)
def scatter(req: ScatterRequest, db: Session = Depends(get_db)):
    if not req.variables or len(req.variables) != 2:
        raise HTTPException(400, "Debe especificar exactamente 2 variables")

    _validate_time_window(req.ts_from, req.ts_to)
    limit = _clamp_limit(req.limit, MAX_SCATTER_POINTS)

    v1, v2 = req.variables

    base = select(
        Medicion.despliegue_id,
        Medicion.variable,
        Medicion.valor,
        Medicion.ts_local_tz,
        Medicion.indicador_calidad,
    )
    base = _apply_filters(base, req, db).subquery("base")

    bucket_expr = _date_bucket(base.c.ts_local_tz, req.align)

    a = select(
        base.c.despliegue_id.label("d1"),
        bucket_expr.label("bucket"),
        base.c.valor.label("x")
    ).where(base.c.variable == v1).subquery("a")

    b = select(
        base.c.despliegue_id.label("d2"),
        bucket_expr.label("bucket"),
        base.c.valor.label("y")
    ).where(base.c.variable == v2).subquery("b")

    j = select(a.c.bucket, a.c.x, b.c.y).where(
        (a.c.d1 == b.c.d2) & (a.c.bucket == b.c.bucket)
    ).order_by(a.c.bucket.asc()).limit(limit)

    rows = db.execute(j).all()

    points = [
        ScatterPoint(
            ts_utc=r[0],
            x=float(r[1]) if r[1] is not None else None,
            y=float(r[2]) if r[2] is not None else None
        )
        for r in rows
    ]

    return ScatterResponse(x_variable=v1, y_variable=v2, points=points)


# ================================
#  ANALYTICS: HISTOGRAM
# ================================

@router.post("/analytics/histogram", response_model=HistogramResponse)
def histogram(req: HistogramRequest, db: Session = Depends(get_db)):

    _validate_time_window(req.ts_from, req.ts_to)
    if req.bins < 1 or req.bins > MAX_HIST_BINS:
        raise HTTPException(400, f"bins debe estar entre 1 y {MAX_HIST_BINS}")

    # 1) MIN/MAX sobre valor, con los mismos filtros (incluyendo calidad)
    q_mm = select(func.min(Medicion.valor), func.max(Medicion.valor)).where(
        Medicion.variable == req.variable
    )
    q_mm = _apply_filters(q_mm, req, db)

    vmin, vmax = db.execute(q_mm).one()

    if vmin is None or vmax is None:
        return HistogramResponse(
            variable=req.variable,
            min=None,
            max=None,
            bins=req.bins,
            buckets=[]
        )

    if vmin == vmax:
        return HistogramResponse(
            variable=req.variable,
            min=float(vmin),
            max=float(vmax),
            bins=1,
            buckets=[
                HistogramBucket(
                    bucket=1,
                    low=float(vmin),
                    high=float(vmax),
                    count=0
                )
            ]
        )

    width = (vmax - vmin) / req.bins

    # Preparar lista de calidades (para SQL textual)
    cal_list = getattr(req, "indicadores_calidad", None)
    if not cal_list:
        cal_one = getattr(req, "indicador_calidad", None)
        if cal_one is not None:
            cal_list = [cal_one]

    sql = text("""
        SELECT
          width_bucket(m.valor, :vmin, :vmax, :bins) AS b,
          MIN(m.valor) AS low,
          MAX(m.valor) AS high,
          COUNT(*) AS cnt
        FROM iot.mediciones m
        JOIN iot.despliegues d ON d.despliegue_id = m.despliegue_id
        JOIN iot.assets a      ON a.asset_id      = d.asset_id
        JOIN iot.motores mo    ON mo.motor_id     = d.motor_id
        WHERE m.variable = :var
          AND (:from_ts IS NULL OR m.ts_local_tz >= :from_ts)
          AND (:to_ts   IS NULL OR m.ts_local_tz <= :to_ts)
          AND (:despliegue_id IS NULL OR m.despliegue_id = :despliegue_id)
          AND (:asset_codigo  IS NULL OR a.asset_codigo = :asset_codigo)
          AND (:motor_codigo  IS NULL OR mo.motor_codigo = :motor_codigo)
          AND (
                :has_calidad = FALSE
                OR m.indicador_calidad = ANY(:calidades)
              )
        GROUP BY b
        ORDER BY b
    """)

    rows = db.execute(sql, {
        "vmin": vmin,
        "vmax": vmax,
        "bins": req.bins,
        "var": req.variable,
        "from_ts": req.ts_from,
        "to_ts": req.ts_to,
        "despliegue_id": req.despliegue_id,
        "asset_codigo": req.asset_codigo,
        "motor_codigo": req.motor_codigo,
        "has_calidad": bool(cal_list),
        "calidades": cal_list if cal_list else [0],  # dummy si no se usa
    }).all()

    buckets = [
        HistogramBucket(
            bucket=int(r.b),
            low=float(r.low) if r.low is not None else float(vmin),
            high=float(r.high) if r.high is not None else float(vmin + width),
            count=int(r.cnt)
        )
        for r in rows
    ]

    return HistogramResponse(
        variable=req.variable,
        min=float(vmin),
        max=float(vmax),
        bins=req.bins,
        buckets=buckets
    )


# ================================
#  AVAILABLE VARIABLES
# ================================

@router.get("/analytics/available-variables", response_model=AvailableVariablesResponse)
def available_variables(
    despliegue_id: Optional[int] = None,
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    class _R:
        pass

    req = _R()
    req.despliegue_id = despliegue_id
    req.asset_codigo = asset_codigo
    req.motor_codigo = motor_codigo
    req.ts_from = ts_from
    req.ts_to = ts_to
    # si algún día quieres filtrar también por calidad aquí, puedes añadir:
    # req.indicadores_calidad = [...]

    q = select(Medicion.variable).distinct()
    q = _apply_filters(q, req, db).order_by(Medicion.variable.asc())

    vars_ = [r[0] for r in db.execute(q).all()]
    return AvailableVariablesResponse(variables=vars_)


# ================================
#  EXPORT CSV
# ================================

@router.get("/analytics/export-csv")
def export_csv(
    variables: List[str],
    despliegue_id: Optional[int] = None,
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    limit: int = 200_000,
    db: Session = Depends(get_db)
):
    if not variables:
        raise HTTPException(400, "Debe especificar al menos una variable")

    _validate_time_window(ts_from, ts_to)
    limit = _clamp_limit(limit, MAX_EXPORT_ROWS)

    class _R:
        pass

    req = _R()
    req.despliegue_id = despliegue_id
    req.asset_codigo = asset_codigo
    req.motor_codigo = motor_codigo
    req.ts_from = ts_from
    req.ts_to = ts_to
    # igual, aquí podrías añadir req.indicadores_calidad si quieres

    q = select(
        Medicion.ts_local_tz,
        Medicion.variable,
        Medicion.valor,
        Medicion.despliegue_id
    ).where(Medicion.variable.in_(variables))

    q = _apply_filters(q, req, db).order_by(Medicion.ts_local_tz.asc()).limit(limit)

    rows = db.execute(q).all()

    def _gen() -> Iterable[bytes]:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ts_local_tz", "variable", "valor", "despliegue_id"])
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)

        for r in rows:
            w.writerow([r.ts_local_tz.isoformat(), r.variable, r.valor, r.despliegue_id])
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        _gen(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mediciones.csv"}
    )
