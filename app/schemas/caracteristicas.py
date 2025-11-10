# app/schemas/caracteristicas.py
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional


class CaracteristicaBase(BaseModel):
    despliegue_id: int
    ts_utc: datetime
    variable: str = Field(..., max_length=70)
    caracteristica: str = Field(..., max_length=100)
    valor: Optional[Decimal] = None
    ventana_s: int
    indicador_calidad: int = 0


class CaracteristicaCreate(CaracteristicaBase):
    pass


class CaracteristicaUpdate(BaseModel):
    ts_utc: Optional[datetime] = None
    variable: Optional[str] = Field(None, max_length=70)
    caracteristica: Optional[str] = Field(None, max_length=100)
    valor: Optional[Decimal] = None
    ventana_s: Optional[int] = None
    indicador_calidad: Optional[int] = None

    class Config:
        extra = "forbid"


class CaracteristicaRead(CaracteristicaBase):
    caracteristica_id: int
    ts_local_tz: Optional[datetime] = None
    generado_en: datetime

    class Config:
        from_attributes = True  # (orm_mode en Pydantic v1)
