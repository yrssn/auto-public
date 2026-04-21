import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import User, ModelConfig, ImageTask
from schemas import ImageTaskOut
from auth import get_current_user
from services.image_service import generate_image

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/api/image-gen", tags=["图片生成"])


@router.post("/", response_model=ImageTaskOut)
async def create_image_task(
    prompt: str = Form(...),
    model_config_id: Optional[int] = Form(None),
    optimize_prompt: bool = Form(True),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Resolve model config
    config = None
    if model_config_id:
        config = (
            db.query(ModelConfig)
            .filter(
                ModelConfig.id == model_config_id,
                ModelConfig.owner_id == current_user.id,
            )
            .first()
        )
    else:
        config = (
            db.query(ModelConfig)
            .filter(
                ModelConfig.owner_id == current_user.id, ModelConfig.is_default == True
            )
            .first()
        )

    if not config:
        raise HTTPException(status_code=400, detail="请先配置模型或指定模型配置ID")

    # Save uploaded image
    uploaded_image_path = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1] or ".png"
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        content = await image.read()
        with open(filepath, "wb") as f:
            f.write(content)
        uploaded_image_path = f"/uploads/{filename}"

    task = ImageTask(
        prompt=prompt,
        uploaded_image=uploaded_image_path,
        status="generating",
        owner_id=current_user.id,
        model_config_id=config.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        result = await generate_image(
            prompt=prompt,
            optimize=optimize_prompt,
            image_path=os.path.join(UPLOAD_DIR, filename) if uploaded_image_path else None,
            api_key=config.api_key,
            base_url=config.base_url,
            model_name=config.model_name,
        )
        task.optimized_prompt = result.get("optimized_prompt")
        task.result_image_url = result.get("image_url")
        task.status = "done"
    except Exception as e:
        task.status = "failed"
        task.error_msg = str(e)

    db.commit()
    db.refresh(task)
    return task


@router.get("/", response_model=List[ImageTaskOut])
def list_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(ImageTask)
        .filter(ImageTask.owner_id == current_user.id)
        .order_by(ImageTask.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/{task_id}", response_model=ImageTaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = (
        db.query(ImageTask)
        .filter(ImageTask.id == task_id, ImageTask.owner_id == current_user.id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
