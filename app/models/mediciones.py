# app/models/mediciones.py
from sqlalchemy import Column, BigInteger, Text, Numeric, DateTime, Computed, text, ForeignKey
from ..database import Base

class Medicion(Base):
    __tablename__ = "mediciones"
    __table_args__ = {"schema": "iot"}

    medicion_id   = Column(BigInteger, primary_key=True, autoincrement=True)
    despliegue_id = Column(
        BigInteger,
        ForeignKey("iot.despliegues.despliegue_id", ondelete="CASCADE"),
        nullable=False,
    )

    # DB: timestamptz
    ts_utc = Column(DateTime(timezone=True), nullable=False)

   
    ts_local = Column(
        "ts_local_tz",                      
        DateTime(timezone=False),
        Computed("(ts_utc AT TIME ZONE 'America/Guayaquil')", persisted=True),
        nullable=True,
    )

    variable       = Column(Text, nullable=False)
    valor          = Column(Numeric, nullable=True)
    archivo_origen = Column(Text, nullable=True)
    importado_en   = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
