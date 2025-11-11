from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

class IngestaBase(BaseModel):
    asset_codigo: str
    motor_codigo: str
    ts_utc: datetime
    ts_local_tz: Optional[datetime] = None 
    variable: str
    valor: Optional[Decimal] = None
    archivo_origen: Optional[str] = None

class IngestaCreate(BaseModel):
   
    asset_codigo: str
    motor_codigo: str
    ts_utc: datetime
    variable: str
    valor: Optional[Decimal] = None
    archivo_origen: Optional[str] = None

class IngestaUpdate(BaseModel):
    # no se actualizan claves; solo campos de dato
    valor: Optional[Decimal] = None
    archivo_origen: Optional[str] = None

class IngestaRead(IngestaBase):
    ingesta_id: int
    recibido_en: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class IngestaListResponse(BaseModel):
    total: int
    items: List[IngestaRead]
