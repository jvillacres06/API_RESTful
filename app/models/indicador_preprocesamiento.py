from sqlalchemy import Column, SmallInteger, String
from ..database import Base


class IndicadorPreprocesamiento(Base):
    __tablename__ = "indicador_preprocesamiento"
    __table_args__ = {"schema": "iot"}

    codigo_calidad = Column(SmallInteger, primary_key=True, index=True)
    nombre_estado = Column(String(50), nullable=False)
    severidad = Column(SmallInteger, nullable=False, default=0)
    descripcion = Column(String(200), nullable=True)
