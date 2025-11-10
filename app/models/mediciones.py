# app/models/mediciones.py
from sqlalchemy import (
    Column, BigInteger, Text, Numeric, DateTime,
    Computed, text, ForeignKey, SmallInteger
)
from ..database import Base

class Medicion(Base):
    __tablename__ = "mediciones"
    __table_args__ = {"schema": "iot"}

    medicion_id   = Column(BigInteger, primary_key=True, autoincrement=True)
    despliegue_id = Column(
        BigInteger,
        ForeignKey("iot.despliegues.despliegue_id", ondelete="CASCADE"),
        nullable=False
    )

    # TIMESTAMPTZ en BD
    ts_utc = Column(DateTime(timezone=True), nullable=False)

    # Columna generada en BD (ts_local_tz)
    ts_local_tz = Column(
        DateTime(timezone=True),
        Computed(
            "(ts_utc AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')",
            persisted=True
        ),
        nullable=True
    )

    variable = Column(Text, nullable=False)   # FK a iot.variables(variable) en BD
    valor    = Column(Numeric, nullable=True)

    indicador_calidad = Column(
        SmallInteger,
        ForeignKey("iot.indicador_calidad.codigo_calidad"),
        server_default=text("0"),
        nullable=False
    )

    archivo_origen = Column(Text, nullable=True)

    importado_en = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False
    )
