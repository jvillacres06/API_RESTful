from pydantic import BaseModel
from typing import Optional


class IndicadorPreprocBase(BaseModel):
    codigo_calidad: int
    nombre_estado: str
    severidad: int
    descripcion: Optional[str] = None


class IndicadorPreprocCreate(IndicadorPreprocBase):
    pass


class IndicadorPreprocUpdate(BaseModel):
    nombre_estado: Optional[str] = None
    severidad: Optional[int] = None
    descripcion: Optional[str] = None


class IndicadorPreprocRead(IndicadorPreprocBase):
    class Config:
        orm_mode = True
