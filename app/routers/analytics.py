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
    AvailableVariablesResponse
)

router = APIRouter()

# -------------------------------
# Reglas de negocio
# -------------------------------

MAX_TREND_POINTS: int = 10_000
MAX_SCATTER_POINTS: int = 10_000
MAX_HIST_BINS: int = 200
MAX_EXPORT_ROWS: int = 200_000
MAX_VARIABLES_TREND: int = 10  # máximo de variables en /trend


def _clamp_limit(limit: int, max_limit: int) -> int:
    return max(1, min(limit, max_limit))


def _validate_time_window(ts_from: Optional[datetime], ts_to: Optional[datetime]):
    if ts_from and ts_to and ts_from > ts_to:
        raise HTTPException(status_code=400, detail="ts_from no puede ser mayor que ts_to")


# -------------------------------
# Helpers
# -------------------------------

def _apply_filters(q, req, db: Session):
    """
    Aplica filtros opcionales por despliegue/asset/motor y rango de fechas
    al selectable recibido y retorna el selectable resultante.
    """
    conds = []

    if getattr(req, "ts_from", None) is not None:
        conds.append(Medicion.ts_utc >= req.ts_from)
    if getattr(req, "ts_to", None) is not None:
        conds.append(Medicion.ts_utc <= req.ts_to)

    if getattr(req, "despliegue_id", None):
        conds.append(Medicion.despliegue_id == req.despliegue_id)
        return q.where(and_(*conds))

    # Si filtra por asset/motor se hace JOIN con despliegues/assets/motores
    join_needed = (getattr(req, "asset_codigo", None) is not None) or (getattr(req, "motor_codigo", None) is not None)
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


def _date_trunc_unit(align: str):
    if align == "minute":
        return "minute"
    if align == "hour":
        return "hour"
    return None  # exact


# -------------------------------
# Endpoints
# -------------------------------

@router.post("/analytics/trend", response_model=TrendResponse, summary="Series de tiempo por variable")
def trend(req: TrendRequest, db: Session = Depends(get_db)):
    # Reglas de negocio
    if not req.variables:
        raise HTTPException(status_code=400, detail="Debe especificar al menos una variable")
    if len(req.variables) > MAX_VARIABLES_TREND:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo {MAX_VARIABLES_TREND} variables permitidas en trend"
        )

    _validate_time_window(req.ts_from, req.ts_to)
    limit = _clamp_limit(req.limit, MAX_TREND_POINTS)

    series_out: List[Series] = []

    for var in req.variables:
        q = select(Medicion.ts_utc, Medicion.valor).where(Medicion.variable == var)
        q = _apply_filters(q, req, db).order_by(Medicion.ts_utc.asc()).limit(limit)

        rows = db.execute(q).all()
        points = [
            Point(
                ts_utc=r[0],
                valor=float(r[1]) if r[1] is not None else None
            )
            for r in rows
        ]
        series_out.append(Series(variable=var, points=points))

    return TrendResponse(series=series_out)


@router.post("/analytics/scatter", response_model=ScatterResponse, summary="Pares X/Y entre dos variables")
def scatter(req: ScatterRequest, db: Session = Depends(get_db)):
    # Reglas de negocio: exactamente 2 variables
    if not req.variables or len(req.variables) != 2:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar exactamente 2 variables en 'variables' para el scatter"
        )

    _validate_time_window(req.ts_from, req.ts_to)
    limit = _clamp_limit(req.limit, MAX_SCATTER_POINTS)

    v1, v2 = req.variables[0], req.variables[1]
    unit = _date_trunc_unit(req.align)

    # Tabla base con filtros comunes
    base = select(
        Medicion.despliegue_id,
        Medicion.variable,
        Medicion.valor,
        Medicion.ts_utc
    )
    base = _apply_filters(base, req, db).subquery("base")

    # Derivadas para cada variable
    if unit:
        tcol = func.date_trunc(unit, base.c.ts_utc).label("bucket_ts")
    else:
        tcol = base.c.ts_utc.label("bucket_ts")

    a = select(
        base.c.despliegue_id.label("d1"),
        tcol,
        base.c.valor.label("x")
    ).where(base.c.variable == v1).subquery("a")

    b = select(
        base.c.despliegue_id.label("d2"),
        tcol,
        base.c.valor.label("y")
    ).where(base.c.variable == v2).subquery("b")

    # Join por despliegue y bucket de tiempo
    j = select(a.c.bucket_ts, a.c.x, b.c.y).where(
        and_(a.c.d1 == b.c.d2, a.c.bucket_ts == b.c.bucket_ts)
    ).order_by(a.c.bucket_ts.asc()).limit(limit)

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


@router.post("/analytics/histogram", response_model=HistogramResponse, summary="Histograma server-side")
def histogram(req: HistogramRequest, db: Session = Depends(get_db)):
    # Reglas de negocio
    if req.bins < 1 or req.bins > MAX_HIST_BINS:
        raise HTTPException(
            status_code=400,
            detail=f"bins debe estar entre 1 y {MAX_HIST_BINS}"
        )

    _validate_time_window(req.ts_from, req.ts_to)

    # 1) rango min/max
    q_mm = select(func.min(Medicion.valor), func.max(Medicion.valor)).where(Medicion.variable == req.variable)
    q_mm = _apply_filters(q_mm, req, db)
    vmin, vmax = db.execute(q_mm).one()

    if vmin is None or vmax is None:
        return HistogramResponse(variable=req.variable, min=None, max=None, bins=req.bins, buckets=[])

    if vmin == vmax:
        # todos iguales: un bucket
        bucket = HistogramBucket(bucket=1, low=float(vmin), high=float(vmax), count=0)
        return HistogramResponse(
            variable=req.variable,
            min=float(vmin),
            max=float(vmax),
            bins=1,
            buckets=[bucket]
        )

    # 2) contar con width_bucket
    width = (vmax - vmin) / req.bins
    # Nota: usamos SQL textual para width_bucket y límites
    sql = text("""
        SELECT
          width_bucket(valor, :vmin, :vmax, :bins) AS b,
          MIN(valor) AS low,
          MAX(valor) AS high,
          COUNT(*)   AS cnt
        FROM iot.mediciones m
        JOIN iot.despliegues d ON d.despliegue_id = m.despliegue_id
        JOIN iot.assets a ON a.asset_id = d.asset_id
        JOIN iot.motores mo ON mo.motor_id = d.motor_id
        WHERE m.variable = :var
          AND (:from_ts IS NULL OR m.ts_utc >= :from_ts)
          AND (:to_ts   IS NULL OR m.ts_utc <= :to_ts)
          AND (:despliegue_id IS NULL OR m.despliegue_id = :despliegue_id)
          AND (:asset_codigo  IS NULL OR a.asset_codigo = :asset_codigo)
          AND (:motor_codigo  IS NULL OR mo.motor_codigo = :motor_codigo)
        GROUP BY b
        ORDER BY b
    """)
    rows = db.execute(sql, {
        "vmin": vmin, "vmax": vmax, "bins": req.bins, "var": req.variable,
        "from_ts": req.ts_from, "to_ts": req.ts_to,
        "despliegue_id": req.despliegue_id,
        "asset_codigo": req.asset_codigo, "motor_codigo": req.motor_codigo
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
        min=float(vmin), max=float(vmax),
        bins=req.bins,
        buckets=buckets
    )


@router.get("/analytics/available-variables", response_model=AvailableVariablesResponse, summary="Variables disponibles")
def available_variables(
    despliegue_id: Optional[int] = None,
    asset_codigo: Optional[str] = None,
    motor_codigo: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    _validate_time_window(ts_from, ts_to)

    # Armamos un request sintético para reusar _apply_filters
    class _R:
        pass

    req = _R()
    req.despliegue_id = despliegue_id
    req.asset_codigo = asset_codigo
    req.motor_codigo = motor_codigo
    req.ts_from = ts_from
    req.ts_to = ts_to

    q = select(Medicion.variable).distinct()
    q = _apply_filters(q, req, db).order_by(Medicion.variable.asc())

    vars_ = [r[0] for r in db.execute(q).all()]
    return AvailableVariablesResponse(variables=vars_)


@router.get("/analytics/export-csv", summary="Exportar mediciones a CSV")
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
        raise HTTPException(status_code=400, detail="Debe especificar al menos una variable")

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

    q = select(
        Medicion.ts_utc,
        Medicion.variable,
        Medicion.valor,
        Medicion.despliegue_id
    ).where(Medicion.variable.in_(variables))

    q = _apply_filters(q, req, db).order_by(Medicion.ts_utc.asc()).limit(limit)

    rows = db.execute(q).all()

    # stream CSV
    def _gen() -> Iterable[bytes]:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ts_utc", "variable", "valor", "despliegue_id"])
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)

        for r in rows:
            w.writerow([r.ts_utc.isoformat(), r.variable, r.valor, r.despliegue_id])
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        _gen(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mediciones.csv"}
    )
