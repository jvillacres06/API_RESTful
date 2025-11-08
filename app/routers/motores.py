from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.motores import Motor
from ..schemas.motores import MotorCreate, MotorRead, MotorUpdate

router = APIRouter()

@router.get("/", response_model=List[MotorRead])
def list_motores(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Motor).limit(limit).all()

@router.post("/", response_model=MotorRead, status_code=status.HTTP_201_CREATED)
def create_motor(payload: MotorCreate, db: Session = Depends(get_db)):
    if db.query(Motor).filter(Motor.motor_codigo == payload.motor_codigo).first():
        raise HTTPException(400, "motor_codigo ya existe")
    m = Motor(**payload.dict()); db.add(m); db.commit(); db.refresh(m)
    return m

@router.get("/{motor_id}", response_model=MotorRead)
def get_motor(motor_id: int, db: Session = Depends(get_db)):
    m = db.query(Motor).filter(Motor.motor_id == motor_id).first()
    if not m:
        raise HTTPException(404, "Motor no encontrado")
    return m

@router.put("/{motor_id}", response_model=MotorRead)
def update_motor(motor_id: int, payload: MotorUpdate, db: Session = Depends(get_db)):
    m = db.query(Motor).filter(Motor.motor_id == motor_id).first()
    if not m:
        raise HTTPException(404, "Motor no encontrado")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit(); db.refresh(m)
    return m

@router.delete("/{motor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_motor(motor_id: int, db: Session = Depends(get_db)):
    m = db.query(Motor).filter(Motor.motor_id == motor_id).first()
    if not m:
        raise HTTPException(404, "Motor no encontrado")
    db.delete(m); db.commit()
    return
