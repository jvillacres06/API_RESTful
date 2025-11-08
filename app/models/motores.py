from sqlalchemy import Column, BigInteger, Text
from ..database import Base

class Motor(Base):
    __tablename__ = "motores"
    __table_args__ = {"schema": "iot"}

    motor_id     = Column(BigInteger, primary_key=True)
    motor_codigo = Column(Text, unique=True, nullable=False)
    nombre       = Column(Text)
    ubicacion    = Column(Text)
    notas        = Column(Text)
