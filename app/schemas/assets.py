from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class AssetBase(BaseModel):
    asset_codigo: str
    modelo: Optional[str] = None
    instalado_en: Optional[datetime] = None
    notas: Optional[str] = None

class AssetCreate(AssetBase):
    pass

class AssetUpdate(BaseModel):
    modelo: Optional[str] = None
    instalado_en: Optional[datetime] = None
    notas: Optional[str] = None

class AssetRead(AssetBase):
    asset_id: int
    model_config = ConfigDict(from_attributes=True)
