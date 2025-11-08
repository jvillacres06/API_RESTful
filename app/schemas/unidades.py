from pydantic import BaseModel, ConfigDict

class UnidadBase(BaseModel):
    unidad: str
    descripcion: str

class UnidadCreate(UnidadBase):
    pass

class UnidadUpdate(BaseModel):
    descripcion: str

class UnidadRead(UnidadBase):
    model_config = ConfigDict(from_attributes=True)
