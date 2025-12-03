from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class MedicionBase(BaseModel):
    despliegue_id: int
    ts_utc: datetime
    variable: str
    valor: Optional[float] = None
    indicador_preprocesamiento: int = 0   # NUEVO

class MedicionCreate(MedicionBase):
    pass

class MedicionUpdate(BaseModel):
    valor: Optional[float] = None
    indicador_preprocesamiento: Optional[int] = None

class MedicionRead(MedicionBase):
    medicion_id: int
    ts_local_tz: Optional[datetime] = None
    importado_en: datetime

    class Config:
        from_attributes = True
