import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import User, ModelConfig, ImageTask, Conversation
from schemas import ImageTaskOut, ConversationOut, ConversationDetail
from auth import get_current_user
from services.image_service import generate_image, build_history_messages

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/api/image-gen", tags=["图片生成"])


# ---- Conversation CRUD ----

@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Conversation)
        .filter(Conversation.owner_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = Conversation(title="新会话", owner_id=current_user.id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.owner_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.owner_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.query(ImageTask).filter(ImageTask.conversation_id == conv_id).delete()
    db.delete(conv)
    db.commit()
    return {"detail": "已删除"}


# ---- Generate (with context) ----

@router.post("/conversations/{conv_id}/generate", response_model=ImageTaskOut)
async def create_image_task(
    conv_id: int,
    prompt: str = Form(...),
    model_config_id: Optional[int] = Form(None),
    optimize_prompt: bool = Form(True),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.owner_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Auto-set title from first prompt
    existing_count = db.query(ImageTask).filter(ImageTask.conversation_id == conv_id).count()
    if existing_count == 0:
        conv.title = prompt[:50] if len(prompt) > 0 else "新会话"

    # Resolve model config
    config = None
    if model_config_id:
        config = (
            db.query(ModelConfig)
            .filter(ModelConfig.id == model_config_id, ModelConfig.owner_id == current_user.id)
            .first()
        )
    else:
        config = (
            db.query(ModelConfig)
            .filter(ModelConfig.owner_id == current_user.id, ModelConfig.is_default == True)
            .first()
        )

    if not config:
        raise HTTPException(status_code=400, detail="请先配置模型或指定模型配置ID")

    # Save uploaded image
    uploaded_image_path = None
    saved_filename = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1] or ".png"
        saved_filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOAD_DIR, saved_filename)
        content = await image.read()
        with open(filepath, "wb") as f:
            f.write(content)
        uploaded_image_path = f"/uploads/{saved_filename}"

    task = ImageTask(
        conversation_id=conv_id,
        role="user",
        prompt=prompt,
        uploaded_image=uploaded_image_path,
        status="generating",
        owner_id=current_user.id,
        model_config_id=config.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Build history from previous tasks in this conversation
    history_tasks = (
        db.query(ImageTask)
        .filter(ImageTask.conversation_id == conv_id, ImageTask.id < task.id)
        .order_by(ImageTask.created_at)
        .all()
    )
    history = build_history_messages(history_tasks)

    try:
        result = await generate_image(
            prompt=prompt,
            optimize=optimize_prompt,
            image_path=os.path.join(UPLOAD_DIR, saved_filename) if saved_filename else None,
            api_key=config.api_key,
            base_url=config.base_url,
            model_name=config.model_name,
            history=history,
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
