# app/models/indicador_calidad.py
from sqlalchemy import Column, SmallInteger, String
from ..database import Base

class IndicadorCalidad(Base):
    __tablename__ = "indicador_calidad"
    __table_args__ = {"schema": "iot"}

    codigo_calidad = Column(SmallInteger, primary_key=True)
    nombre_estado  = Column(String(50), unique=True, nullable=False)
    severidad      = Column(SmallInteger, nullable=False)
    descripcion    = Column(String(200), nullable=False)
