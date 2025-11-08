from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from ..database import get_db
from ..models.despliegues import Despliegue
from ..schemas.despliegues import DespliegueCreate, DespliegueRead, DespliegueUpdate

router = APIRouter()

# ---------- Helpers -----------

def _validate_range(inicio, fin):
    if fin is not None and inicio >= fin:
        raise HTTPException(
            status_code=400,
            detail="`inicio` debe ser estrictamente menor que `fin`"
        )

def _assert_no_overlap(
    db: Session,
    asset_id: int,
    motor_id: int,
    inicio,
    fin: Optional[object],   # puede ser None (despliegue activo)
    exclude_id: Optional[int] = None
):
    """
    Regla: no puede haber solape de intervalos para (asset_id, motor_id).
    Intervalo nuevo: [inicio, fin) si fin != None, y [inicio, +∞) si fin == None.
    Se excluye (opcionalmente) un despliegue por ID cuando es update.
    """
    q = db.query(Despliegue).filter(
        Despliegue.asset_id == asset_id,
        Despliegue.motor_id == motor_id
    )
    if exclude_id:
        q = q.filter(Despliegue.despliegue_id != exclude_id)

    if fin is None:
        # Nuevo intervalo es abierto hacia el futuro: [inicio, +∞)
        # Solapa si: (fin_actual IS NULL)  OR  (fin_actual > inicio)
        q = q.filter(
            or_(
                Despliegue.fin.is_(None),
                Despliegue.fin > inicio
            )
        )
    else:
        # Nuevo intervalo [inicio, fin)
        # Solapa si: inicio_actual < fin AND (fin_actual IS NULL OR fin_actual > inicio)
        q = q.filter(
            and_(
                Despliegue.inicio < fin,
                or_(Despliegue.fin.is_(None), Despliegue.fin > inicio)
            )
        )

    conflict = q.first()
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=(
                "Existe un despliegue que se solapa para ese asset/motor. "
                "Cierre el despliegue activo previo o elija un rango sin solape."
            )
        )

def _assert_no_active_duplicate(db: Session, asset_id: int, motor_id: int, exclude_id: Optional[int] = None):
    """
    Si se crea/actualiza un despliegue con fin=None (activo), debe ser el único activo
    para esa pareja asset/motor.
    """
    q = db.query(Despliegue).filter(
        Despliegue.asset_id == asset_id,
        Despliegue.motor_id == motor_id,
        Despliegue.fin.is_(None),
    )
    if exclude_id:
        q = q.filter(Despliegue.despliegue_id != exclude_id)
    if db.query(q.exists()).scalar():
        raise HTTPException(
            status_code=409,
            detail="Ya existe un despliegue activo (fin=NULL) para ese asset/motor."
        )

# ---------- Endpoints -----------

@router.get("/", response_model=List[DespliegueRead])
def list_despliegues(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Despliegue).limit(limit).all()

@router.post("/", response_model=DespliegueRead, status_code=status.HTTP_201_CREATED)
def create_despliegue(payload: DespliegueCreate, db: Session = Depends(get_db)):
    # Validaciones de rango y solape
    _validate_range(payload.inicio, payload.fin)

    # Si fin=None, verificar que no haya otro activo
    if payload.fin is None:
        _assert_no_active_duplicate(db, payload.asset_id, payload.motor_id)

    # Verificar solapes con otros intervalos
    _assert_no_overlap(db, payload.asset_id, payload.motor_id, payload.inicio, payload.fin)

    d = Despliegue(**payload.dict())
    db.add(d)
    db.commit()
    db.refresh(d)
    return d

@router.put("/{despliegue_id}", response_model=DespliegueRead)
def update_despliegue(despliegue_id: int, payload: DespliegueUpdate, db: Session = Depends(get_db)):
    d = db.query(Despliegue).filter(Despliegue.despliegue_id == despliegue_id).first()
    if not d:
        raise HTTPException(404, "Despliegue no encontrado")

    # Tomar valores resultantes (nuevos si vienen, sino los actuales)
    new_asset_id = payload.asset_id if payload.asset_id is not None else d.asset_id
    new_motor_id = payload.motor_id if payload.motor_id is not None else d.motor_id
    new_inicio   = payload.inicio   if payload.inicio   is not None else d.inicio
    new_fin      = payload.fin      if payload.fin      is not None else d.fin

    # Validaciones
    _validate_range(new_inicio, new_fin)
    if new_fin is None:
        _assert_no_active_duplicate(db, new_asset_id, new_motor_id, exclude_id=despliegue_id)
    _assert_no_overlap(db, new_asset_id, new_motor_id, new_inicio, new_fin, exclude_id=despliegue_id)

    # Aplicar cambios
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d

@router.delete("/{despliegue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_despliegue(despliegue_id: int, db: Session = Depends(get_db)):
    d = db.query(Despliegue).filter(Despliegue.despliegue_id == despliegue_id).first()
    if not d:
        raise HTTPException(404, "Despliegue no encontrado")
    db.delete(d)
    db.commit()
    return
