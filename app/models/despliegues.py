from sqlalchemy import Column, BigInteger, ForeignKey
from sqlalchemy import DateTime

from ..database import Base

class Despliegue(Base):
    __tablename__ = "despliegues"
    __table_args__ = {"schema": "iot"}

    despliegue_id = Column(BigInteger, primary_key=True)
    asset_id      = Column(BigInteger, ForeignKey("iot.assets.asset_id", ondelete="CASCADE"), nullable=False)
    motor_id      = Column(BigInteger, ForeignKey("iot.motores.motor_id", ondelete="RESTRICT"), nullable=False)
    inicio        = Column(DateTime(timezone=True), nullable=False)  # antes TIMESTAMPTZ
    fin           = Column(DateTime(timezone=True))   # periodo es GENERATED en BD
