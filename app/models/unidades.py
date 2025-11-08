from sqlalchemy import Column, Text
from ..database import Base

class Unidad(Base):
    __tablename__ = "unidades"
    __table_args__ = {"schema": "iot"}

    unidad = Column(Text, primary_key=True)
    descripcion = Column(Text, nullable=False)
