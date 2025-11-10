# app/models/caracteristicas.py
from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    Text,
    Numeric,
    DateTime,
    SmallInteger,
    ForeignKey,
    Computed,
    text,
)
from ..database import Base


class Caracteristica(Base):
    __tablename__ = "caracteristicas"
    __table_args__ = {"schema": "iot"}

    caracteristica_id = Column(BigInteger, primary_key=True, autoincrement=True)

    despliegue_id = Column(
        BigInteger,
        ForeignKey("iot.despliegues.despliegue_id", ondelete="CASCADE"),
        nullable=False,
    )

    # TIMESTAMPTZ en BD
    ts_utc = Column(DateTime(timezone=True), nullable=False)

    # Generada SIEMPRE por el servidor (TIMESTAMPTZ)
    ts_local_tz = Column(
        DateTime(timezone=True),
        Computed(
            "(ts_utc AT TIME ZONE 'UTC' AT TIME ZONE 'America/Guayaquil')",
            persisted=True,
        ),
        nullable=True,
    )

    variable = Column(Text, nullable=False)         # FK a iot.variables(variable)
    caracteristica = Column(Text, nullable=False)   # nombre de la feature
    valor = Column(Numeric, nullable=True)
    ventana_s = Column(Integer, nullable=False)

    indicador_calidad = Column(
        SmallInteger,
        ForeignKey("iot.indicador_calidad.codigo_calidad"),
        nullable=False,
        server_default=text("0"),
    )

    generado_en = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
