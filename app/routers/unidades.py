from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models.unidades import Unidad
from ..schemas.unidades import UnidadCreate, UnidadRead, UnidadUpdate

router = APIRouter()

@router.get("/", response_model=List[UnidadRead])
def list_unidades(db: Session = Depends(get_db)):
    return db.query(Unidad).all()

@router.post("/", response_model=UnidadRead, status_code=status.HTTP_201_CREATED)
def create_unidad(payload: UnidadCreate, db: Session = Depends(get_db)):
    if db.query(Unidad).filter(Unidad.unidad == payload.unidad).first():
        raise HTTPException(400, "Unidad ya existe")
    u = Unidad(**payload.dict())
    db.add(u); db.commit(); db.refresh(u)
    return u

@router.put("/{unidad}", response_model=UnidadRead)
def update_unidad(unidad: str, payload: UnidadUpdate, db: Session = Depends(get_db)):
    u = db.query(Unidad).filter(Unidad.unidad == unidad).first()
    if not u:
        raise HTTPException(404, "Unidad no encontrada")
    for k,v in payload.dict(exclude_unset=True).items():
        setattr(u,k,v)
    db.commit(); db.refresh(u)
    return u

@router.delete("/{unidad}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unidad(unidad: str, db: Session = Depends(get_db)):
    u = db.query(Unidad).filter(Unidad.unidad == unidad).first()
    if not u:
        raise HTTPException(404, "Unidad no encontrada")
    db.delete(u); db.commit()
    return
