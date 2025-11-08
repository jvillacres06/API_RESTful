# app/models/ingestas.py
from sqlalchemy import Column, Integer, String, DateTime, Numeric, text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Ingesta(Base):
    __tablename__ = "ingestas"
    __table_args__ = {"schema": "raw"}

    ingesta_id   = Column(Integer, primary_key=True, index=True)
    asset_codigo = Column(String(50), nullable=True)
    motor_codigo = Column(String(50), nullable=True)

    # UTC real
    ts_utc       = Column(DateTime(timezone=True), nullable=False)

    # IMPORTANTE: nombre real en la BD
    ts_local_tz  = Column("ts_local_tz", DateTime(timezone=True), nullable=True)  # generada

    variable     = Column(String(100), nullable=False)
    valor        = Column(Numeric, nullable=True)
    archivo_origen = Column(String(50), nullable=True)

    recibido_en  = Column(DateTime(timezone=True), server_default=text("now()"))
