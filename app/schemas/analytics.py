# app/schemas/analytics.py

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


# ---------------------------------
# Base de filtros comunes
# ---------------------------------

class BaseFiltrosMediciones(BaseModel):
    despliegue_id: Optional[int] = None
    asset_codigo: Optional[str] = None
    motor_codigo: Optional[str] = None
    ts_from: Optional[datetime] = None
    ts_to: Optional[datetime] = None

    # Calidad: uno o varios valores
    indicador_calidad: Optional[int] = None
    indicadores_calidad: Optional[List[int]] = None


# ---------------------------------
# TREND
# ---------------------------------

class Point(BaseModel):
    ts_utc: datetime   # en realidad ts_local_tz, pero se mantiene el nombre por compatibilidad
    valor: Optional[float]


class Series(BaseModel):
    variable: str
    points: List[Point]


class TrendRequest(BaseFiltrosMediciones):
    variables: List[str]
    limit: int = 1000


class TrendResponse(BaseModel):
    series: List[Series]


# ---------------------------------
# SCATTER
# ---------------------------------

class ScatterPoint(BaseModel):
    ts_utc: datetime
    x: Optional[float]
    y: Optional[float]


class ScatterRequest(BaseFiltrosMediciones):
    variables: List[str]          # exactamente 2 variables
    limit: int = 1000
    align: str = "exact"          # "exact", "minute", "hour" (se usa en el backend)


class ScatterResponse(BaseModel):
    x_variable: str
    y_variable: str
    points: List[ScatterPoint]


# ---------------------------------
# HISTOGRAM
# ---------------------------------

class HistogramBucket(BaseModel):
    bucket: int
    low: float
    high: float
    count: int


class HistogramRequest(BaseFiltrosMediciones):
    variable: str
    bins: int = 20


class HistogramResponse(BaseModel):
    variable: str
    min: Optional[float]
    max: Optional[float]
    bins: int
    buckets: List[HistogramBucket]


# ---------------------------------
# AVAILABLE VARIABLES
# ---------------------------------

class AvailableVariablesResponse(BaseModel):
    variables: List[str]
