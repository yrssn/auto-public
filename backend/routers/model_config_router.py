from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import User, ModelConfig
from schemas import ModelConfigCreate, ModelConfigUpdate, ModelConfigOut
from auth import get_current_user

router = APIRouter(prefix="/api/model-configs", tags=["模型配置"])


@router.get("/", response_model=List[ModelConfigOut])
def list_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(ModelConfig).filter(ModelConfig.owner_id == current_user.id).all()


@router.post("/", response_model=ModelConfigOut)
def create_config(
    payload: ModelConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.is_default:
        db.query(ModelConfig).filter(
            ModelConfig.owner_id == current_user.id, ModelConfig.is_default == True
        ).update({"is_default": False})

    config = ModelConfig(**payload.model_dump(), owner_id=current_user.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.put("/{config_id}", response_model=ModelConfigOut)
def update_config(
    config_id: int,
    payload: ModelConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = (
        db.query(ModelConfig)
        .filter(ModelConfig.id == config_id, ModelConfig.owner_id == current_user.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    update_data = payload.model_dump(exclude_unset=True)
    if update_data.get("is_default"):
        db.query(ModelConfig).filter(
            ModelConfig.owner_id == current_user.id,
            ModelConfig.is_default == True,
            ModelConfig.id != config_id,
        ).update({"is_default": False})

    for k, v in update_data.items():
        setattr(config, k, v)
    db.commit()
    db.refresh(config)
    return config


@router.delete("/{config_id}")
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = (
        db.query(ModelConfig)
        .filter(ModelConfig.id == config_id, ModelConfig.owner_id == current_user.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    db.delete(config)
    db.commit()
    return {"detail": "已删除"}
