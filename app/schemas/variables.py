from pydantic import BaseModel, ConfigDict
from typing import Optional

class VariableBase(BaseModel):
    variable: str
    unidad: str
    cname: Optional[str] = None

class VariableCreate(VariableBase):
    pass

class VariableUpdate(BaseModel):
    unidad: Optional[str] = None
    cname: Optional[str] = None

class VariableRead(VariableBase):
    model_config = ConfigDict(from_attributes=True)
