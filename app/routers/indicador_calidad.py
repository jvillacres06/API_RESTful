# app/routers/indicador_calidad.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..models.indicador_calidad import IndicadorCalidad
from ..schemas.indicador_calidad import (
    IndicadorCalidadCreate,
    IndicadorCalidadRead,
    IndicadorCalidadUpdate,
)

router = APIRouter()

@router.get("/", response_model=List[IndicadorCalidadRead])
def list_indicadores(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(IndicadorCalidad).order_by(IndicadorCalidad.codigo_calidad.asc())
    return q.offset(offset).limit(limit).all()


@router.get("/{codigo_calidad}", response_model=IndicadorCalidadRead)
def get_indicador(codigo_calidad: int, db: Session = Depends(get_db)):
    row = (
        db.query(IndicadorCalidad)
        .filter(IndicadorCalidad.codigo_calidad == codigo_calidad)
        .first()
    )
    if not row:
        raise HTTPException(404, "Indicador de calidad no encontrado")
    return row


@router.post("/", response_model=IndicadorCalidadRead, status_code=status.HTTP_201_CREATED)
def create_indicador(payload: IndicadorCalidadCreate, db: Session = Depends(get_db)):
    # pequeño check para evitar códigos duplicados a nivel aplicación
    exists = (
        db.query(IndicadorCalidad)
        .filter(IndicadorCalidad.codigo_calidad == payload.codigo_calidad)
        .first()
    )
    if exists:
        raise HTTPException(409, "codigo_calidad ya existe")

    row = IndicadorCalidad(**payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{codigo_calidad}", response_model=IndicadorCalidadRead)
def update_indicador(
    codigo_calidad: int,
    payload: IndicadorCalidadUpdate,
    db: Session = Depends(get_db),
):
    row = (
        db.query(IndicadorCalidad)
        .filter(IndicadorCalidad.codigo_calidad == codigo_calidad)
        .first()
    )
    if not row:
        raise HTTPException(404, "Indicador de calidad no encontrado")

    data = payload.dict(exclude_unset=True)
    # no permitir cambiar el PK desde el body
    data.pop("codigo_calidad", None)

    for k, v in data.items():
        setattr(row, k, v)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{codigo_calidad}", status_code=status.HTTP_204_NO_CONTENT)
def delete_indicador(codigo_calidad: int, db: Session = Depends(get_db)):
    row = (
        db.query(IndicadorCalidad)
        .filter(IndicadorCalidad.codigo_calidad == codigo_calidad)
        .first()
    )
    if not row:
        raise HTTPException(404, "Indicador de calidad no encontrado")

    # OJO: si hay mediciones/características que lo usan, el FK en la BD
    # impedirá el borrado. Eso está bien para mantener integridad.
    db.delete(row)
    db.commit()
    return
