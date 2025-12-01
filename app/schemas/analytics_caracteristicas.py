# app/schemas/analytics_caracteristicas.py

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


# ---------------------------------
# Base de filtros comunes
# ---------------------------------

class BaseFiltrosCaracteristicas(BaseModel):
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

class CaracPoint(BaseModel):
    ts_local_tz: datetime
    valor: Optional[float]


class CaracSeries(BaseModel):
    variable: str
    caracteristica: str
    nombre: str
    points: List[CaracPoint]


class CaracTrendRequest(BaseFiltrosCaracteristicas):
    variables: List[str]
    caracteristicas: List[str]
    limit: int = 1000


class CaracTrendResponse(BaseModel):
    series: List[CaracSeries]


# ---------------------------------
# SCATTER
# ---------------------------------

class CaracScatterPoint(BaseModel):
    ts_local_tz: datetime
    x: Optional[float]
    y: Optional[float]


class CaracScatterRequest(BaseFiltrosCaracteristicas):
    variable: str
    caracteristica_x: str
    caracteristica_y: str
    limit: int = 1000


class CaracScatterResponse(BaseModel):
    variable: str
    x_caracteristica: str
    y_caracteristica: str
    points: List[CaracScatterPoint]


# ---------------------------------
# HISTOGRAM
# ---------------------------------

class CaracHistogramBucket(BaseModel):
    bucket: int
    low: float
    high: float
    count: int


class CaracHistogramRequest(BaseFiltrosCaracteristicas):
    variable: str
    caracteristica: str
    bins: int = 20


class CaracHistogramResponse(BaseModel):
    variable: str
    caracteristica: str
    min: Optional[float]
    max: Optional[float]
    bins: int
    buckets: List[CaracHistogramBucket]


# ---------------------------------
# AVAILABLE VARIABLES / CARACTERÍSTICAS
# ---------------------------------

class CaracAvailableVariablesResponse(BaseModel):
    variables: List[str]


class CaracAvailableCaracteristicasResponse(BaseModel):
    caracteristicas: List[str]
