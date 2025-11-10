from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class MedicionBase(BaseModel):
    despliegue_id: int
    ts_utc: datetime
    variable: str
    valor: Optional[float] = None
    archivo_origen: Optional[str] = None
    indicador_calidad: int = 0   # NUEVO

class MedicionCreate(MedicionBase):
    pass

class MedicionUpdate(BaseModel):
    valor: Optional[float] = None
    indicador_calidad: Optional[int] = None

class MedicionRead(MedicionBase):
    medicion_id: int
    ts_local_tz: Optional[datetime] = None
    importado_en: datetime

    class Config:
        from_attributes = True
