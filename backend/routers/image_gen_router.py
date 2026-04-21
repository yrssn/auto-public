import os
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Optional
from jose import jwt, JWTError

from config import settings
from database import get_db, SessionLocal
from models import User, ModelConfig, ImageTask, Conversation
from schemas import ImageTaskOut, ConversationOut, ConversationDetail
from auth import get_current_user
from services.image_service import generate_image_stream, build_history_messages

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


# ---- Image Upload ----

@router.post("/upload")
async def upload_image(
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    ext = os.path.splitext(image.filename)[1] or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    content = await image.read()
    with open(filepath, "wb") as f:
        f.write(content)
    return {"path": f"/uploads/{filename}", "filename": filename}


# ---- WebSocket Generate ----

def _auth_from_token(token: str) -> Optional[int]:
    """Extract user_id from JWT token, return None on failure."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        uid = payload.get("sub")
        return int(uid) if uid else None
    except (JWTError, ValueError):
        return None


@router.websocket("/conversations/{conv_id}/ws")
async def conversation_ws(websocket: WebSocket, conv_id: int):
    token = websocket.query_params.get("token")
    user_id = _auth_from_token(token) if token else None
    if not user_id:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    db = SessionLocal()

    try:
        conv = db.query(Conversation).filter(
            Conversation.id == conv_id, Conversation.owner_id == user_id
        ).first()
        if not conv:
            await websocket.send_json({"type": "error", "message": "会话不存在"})
            await websocket.close()
            return

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            prompt = data.get("prompt", "").strip()
            uploaded_image = data.get("uploaded_image")
            model_config_id = data.get("model_config_id")
            optimize = data.get("optimize_prompt", True)

            if not prompt and not uploaded_image:
                await websocket.send_json({"type": "error", "message": "请输入描述或上传图片"})
                continue

            if not prompt:
                prompt = "请分析这张商品图片"

            # Resolve chat model (for prompt optimization)
            chat_model = db.query(ModelConfig).filter(
                ModelConfig.owner_id == user_id, ModelConfig.model_type == "chat"
            ).first()
            if not chat_model:
                # Fallback: any model marked as default
                chat_model = db.query(ModelConfig).filter(
                    ModelConfig.owner_id == user_id, ModelConfig.is_default == True
                ).first()
            if not chat_model:
                await websocket.send_json({"type": "error", "message": "请先配置聊天模型（用于优化提示词）"})
                continue

            # Resolve image model (for image generation)
            image_model = None
            if model_config_id:
                image_model = db.query(ModelConfig).filter(
                    ModelConfig.id == model_config_id, ModelConfig.owner_id == user_id
                ).first()
            else:
                image_model = db.query(ModelConfig).filter(
                    ModelConfig.owner_id == user_id, ModelConfig.model_type == "image"
                ).first()

            chat_cfg = {"api_key": chat_model.api_key, "base_url": chat_model.base_url, "model_name": chat_model.model_name}
            image_cfg = None
            if image_model:
                image_cfg = {"api_key": image_model.api_key, "base_url": image_model.base_url, "model_name": image_model.model_name}

            # Auto-set title
            existing = db.query(ImageTask).filter(ImageTask.conversation_id == conv_id).count()
            if existing == 0:
                conv.title = prompt[:50]
                db.commit()

            # Create task
            task = ImageTask(
                conversation_id=conv_id,
                role="user",
                prompt=prompt,
                uploaded_image=uploaded_image,
                status="generating",
                owner_id=user_id,
                model_config_id=image_model.id if image_model else chat_model.id,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id

            await websocket.send_json({
                "type": "task_created",
                "task": _task_dict(task),
            })

            # Build history
            history_tasks = (
                db.query(ImageTask)
                .filter(ImageTask.conversation_id == conv_id, ImageTask.id < task_id)
                .order_by(ImageTask.created_at).all()
            )
            history = build_history_messages(history_tasks)

            # Resolve image path on disk
            image_path = None
            if uploaded_image:
                fname = uploaded_image.split("/")[-1]
                image_path = os.path.join(UPLOAD_DIR, fname)

            # Stream generation
            try:
                async for update in generate_image_stream(
                    prompt=prompt,
                    optimize=optimize,
                    image_path=image_path,
                    chat_config=chat_cfg,
                    image_config=image_cfg,
                    history=history,
                ):
                    await websocket.send_json({"type": "progress", **update})

                    if update.get("step") == "done":
                        result = update.get("result", {})
                        db.rollback()
                        task = db.query(ImageTask).filter(ImageTask.id == task_id).first()
                        task.optimized_prompt = result.get("optimized_prompt")
                        task.result_image_url = result.get("image_url")
                        if result.get("error"):
                            task.status = "failed"
                            task.error_msg = result["error"]
                        else:
                            task.status = "done"
                        db.commit()
                        db.refresh(task)
                        await websocket.send_json({
                            "type": "task_updated",
                            "task": _task_dict(task),
                        })
            except Exception as e:
                db.rollback()
                task = db.query(ImageTask).filter(ImageTask.id == task_id).first()
                if task:
                    task.status = "failed"
                    task.error_msg = str(e)
                    db.commit()
                    db.refresh(task)
                    await websocket.send_json({
                        "type": "task_updated",
                        "task": _task_dict(task),
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        db.close()


def _task_dict(task: ImageTask) -> dict:
    return {
        "id": task.id,
        "conversation_id": task.conversation_id,
        "role": task.role,
        "prompt": task.prompt,
        "uploaded_image": task.uploaded_image,
        "optimized_prompt": task.optimized_prompt,
        "result_image_url": task.result_image_url,
        "status": task.status,
        "error_msg": task.error_msg,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
