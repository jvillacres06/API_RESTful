from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

# ----- Requests -----

class BaseFilter(BaseModel):
    # filtros opcionales
    despliegue_id: Optional[int] = None
    asset_codigo: Optional[str] = None
    motor_codigo: Optional[str] = None
    ts_from: Optional[datetime] = Field(None, description="UTC ISO8601")
    ts_to: Optional[datetime] = Field(None, description="UTC ISO8601")

class TrendRequest(BaseFilter):
    variables: List[str] = Field(..., min_items=1)
    limit: int = Field(10000, ge=1, le=200000)

class ScatterRequest(BaseFilter):
    variables: List[str] = Field(..., min_items=2, max_items=2,
                                 description="Exactamente 2 variables")
    align: Literal["exact", "minute", "hour"] = "minute"
    limit: int = Field(10000, ge=1, le=200000)

class HistogramRequest(BaseFilter):
    variable: str
    bins: int = Field(20, ge=2, le=2000)

# ----- Responses -----

class Point(BaseModel):
    ts_utc: datetime
    valor: Optional[float]

class Series(BaseModel):
    variable: str
    points: List[Point]

class TrendResponse(BaseModel):
    series: List[Series]

class ScatterPoint(BaseModel):
    x: Optional[float]
    y: Optional[float]
    ts_utc: datetime

class ScatterResponse(BaseModel):
    x_variable: str
    y_variable: str
    points: List[ScatterPoint]

class HistogramBucket(BaseModel):
    bucket: int
    low: float
    high: float
    count: int

class HistogramResponse(BaseModel):
    variable: str
    min: Optional[float]
    max: Optional[float]
    bins: int
    buckets: List[HistogramBucket]

class AvailableVariablesResponse(BaseModel):
    variables: List[str]
