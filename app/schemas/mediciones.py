from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from decimal import Decimal

class MedicionBase(BaseModel):
    despliegue_id: int
    ts_utc: datetime
    variable: str
    valor: Optional[Decimal] = None
    archivo_origen: Optional[str] = None

class MedicionCreate(MedicionBase):
    pass

class MedicionUpdate(BaseModel):
    valor: Optional[Decimal] = None
    archivo_origen: Optional[str] = None

class MedicionRead(BaseModel):
    medicion_id: int
    despliegue_id: int
    ts_utc: datetime
    ts_local: Optional[datetime]
    variable: str
    valor: Optional[Decimal]
    archivo_origen: Optional[str]
    importado_en: Optional[datetime]
    asset_codigo: Optional[str]
    motor_codigo: Optional[str]
    model_config = ConfigDict(from_attributes=True)
