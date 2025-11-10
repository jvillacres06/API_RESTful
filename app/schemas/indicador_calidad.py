# app/schemas/indicador_calidad.py
from pydantic import BaseModel

class IndicadorCalidadBase(BaseModel):
    nombre_estado: str
    severidad: int
    descripcion: str

class IndicadorCalidadCreate(IndicadorCalidadBase):
    codigo_calidad: int

class IndicadorCalidadUpdate(BaseModel):
    nombre_estado: str | None = None
    severidad: int | None = None
    descripcion: str | None = None

class IndicadorCalidadRead(IndicadorCalidadBase):
    codigo_calidad: int

    class Config:
        orm_mode = True
