from sqlalchemy import Column, BigInteger, Text
from sqlalchemy import DateTime
from ..database import Base

class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = {"schema": "iot"}

    asset_id     = Column(BigInteger, primary_key=True)
    asset_codigo = Column(Text, unique=True, nullable=False)
    modelo       = Column(Text)
    instalado_en = Column(DateTime(timezone=True)) 
    notas        = Column(Text)
