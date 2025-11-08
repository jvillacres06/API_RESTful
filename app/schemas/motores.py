from pydantic import BaseModel, ConfigDict
from typing import Optional

class MotorBase(BaseModel):
    motor_codigo: str
    nombre: Optional[str] = None
    ubicacion: Optional[str] = None
    notas: Optional[str] = None

class MotorCreate(MotorBase):
    pass

class MotorUpdate(BaseModel):
    nombre: Optional[str] = None
    ubicacion: Optional[str] = None
    notas: Optional[str] = None

class MotorRead(MotorBase):
    motor_id: int
    model_config = ConfigDict(from_attributes=True)
