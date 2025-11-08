from sqlalchemy import Column, Text, ForeignKey
from ..database import Base

class Variable(Base):
    __tablename__ = "variables"
    __table_args__ = {"schema": "iot"}

    variable = Column(Text, primary_key=True)
    unidad   = Column(Text, ForeignKey("iot.unidades.unidad", onupdate="CASCADE"), nullable=False)
    cname    = Column(Text, unique=True)
