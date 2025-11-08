from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class DespliegueBase(BaseModel):
    asset_id: int
    motor_id: int
    inicio: datetime
    fin: Optional[datetime] = None

class DespliegueCreate(DespliegueBase):
    pass

class DespliegueUpdate(BaseModel):
    fin: Optional[datetime] = None

class DespliegueRead(DespliegueBase):
    despliegue_id: int
    model_config = ConfigDict(from_attributes=True)
