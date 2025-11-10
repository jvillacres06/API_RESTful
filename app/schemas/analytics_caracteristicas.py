# app/schemas/analytics_caracteristicas.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class BaseFiltrosCaracteristicas(BaseModel):
    despliegue_id: Optional[int] = None
    asset_codigo: Optional[str] = None
    motor_codigo: Optional[str] = None
    ts_from: Optional[datetime] = None
    ts_to: Optional[datetime] = None


# ---------- Trend ----------

class CaracPoint(BaseModel):
    ts_utc: datetime
    valor: Optional[float]


class CaracSeries(BaseModel):
    variable: str
    caracteristica: str
    nombre: str         # nombre amigable para la serie (por ejemplo "Temp:mean")
    points: List[CaracPoint]


class CaracTrendRequest(BaseFiltrosCaracteristicas):
    variables: List[str]
    caracteristicas: List[str]
    limit: int = 10_000


class CaracTrendResponse(BaseModel):
    series: List[CaracSeries]


# ---------- Scatter ----------

class CaracScatterPoint(BaseModel):
    ts_utc: datetime
    x: Optional[float]
    y: Optional[float]


class CaracScatterRequest(BaseFiltrosCaracteristicas):
    # Regla de negocio: exactamente 1 variable y 2 características
    variable: str
    caracteristica_x: str
    caracteristica_y: str
    align: str = "exact"  # "exact" | "minute" | "hour"
    limit: int = 10_000


class CaracScatterResponse(BaseModel):
    variable: str
    x_caracteristica: str
    y_caracteristica: str
    points: List[CaracScatterPoint]


# ---------- Histogram ----------

class CaracHistogramRequest(BaseFiltrosCaracteristicas):
    variable: str
    caracteristica: str
    bins: int = 50


class CaracHistogramBucket(BaseModel):
    bucket: int
    low: float
    high: float
    count: int


class CaracHistogramResponse(BaseModel):
    variable: str
    caracteristica: str
    min: Optional[float]
    max: Optional[float]
    bins: int
    buckets: List[CaracHistogramBucket]


# ---------- Listas de disponibles ----------

class CaracAvailableVariablesResponse(BaseModel):
    variables: List[str]


class CaracAvailableCaracteristicasResponse(BaseModel):
    caracteristicas: List[str]
