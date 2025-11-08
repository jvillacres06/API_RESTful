from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models.variables import Variable
from ..schemas.variables import VariableCreate, VariableRead, VariableUpdate

router = APIRouter()


@router.get("/", response_model=List[VariableRead])
def list_variables(db: Session = Depends(get_db)):
    return db.query(Variable).all()

@router.post("/", response_model=VariableRead, status_code=status.HTTP_201_CREATED)
def create_variable(payload: VariableCreate, db: Session = Depends(get_db)):
    if db.query(Variable).filter(Variable.variable == payload.variable).first():
        raise HTTPException(400, "Variable ya existe")
    v = Variable(**payload.dict())
    db.add(v); db.commit(); db.refresh(v)
    return v

@router.put("/{variable}", response_model=VariableRead)
def update_variable(variable: str, payload: VariableUpdate, db: Session = Depends(get_db)):
    v = db.query(Variable).filter(Variable.variable == variable).first()
    if not v:
        raise HTTPException(404, "Variable no encontrada")
    for k, val in payload.dict(exclude_unset=True).items():
        setattr(v, k, val)
    db.commit(); db.refresh(v)
    return v

@router.delete("/{variable}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variable(variable: str, db: Session = Depends(get_db)):
    v = db.query(Variable).filter(Variable.variable == variable).first()
    if not v:
        raise HTTPException(404, "Variable no encontrada")
    db.delete(v); db.commit()
    return
