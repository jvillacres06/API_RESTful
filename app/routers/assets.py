from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models.assets import Asset
from ..schemas.assets import AssetCreate, AssetRead, AssetUpdate

router = APIRouter()

@router.get("/", response_model=List[AssetRead])
def list_assets(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Asset).limit(limit).all()

@router.post("/", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db)):
    if db.query(Asset).filter(Asset.asset_codigo == payload.asset_codigo).first():
        raise HTTPException(400, "asset_codigo ya existe")
    a = Asset(**payload.dict()); db.add(a); db.commit(); db.refresh(a)
    return a

@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not a:
        raise HTTPException(404, "Asset no encontrado")
    return a

@router.put("/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: int, payload: AssetUpdate, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not a:
        raise HTTPException(404, "Asset no encontrado")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(a, k, v)
    db.commit(); db.refresh(a)
    return a

@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    a = db.query(Asset).filter(Asset.asset_id == asset_id).first()
    if not a:
        raise HTTPException(404, "Asset no encontrado")
    db.delete(a); db.commit()
    return
