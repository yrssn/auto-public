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
from services.image_service import generate_image_stream

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
            # Close stale session and create fresh one to avoid "MySQL server has gone away"
            db.close()
            db = SessionLocal()

            raw = await websocket.receive_text()
            data = json.loads(raw)

            prompt = data.get("prompt", "").strip()
            # Support both single product_image (legacy) and multiple product_images
            product_images = data.get("product_images") or []
            product_image = data.get("product_image")
            if not product_images and product_image:
                product_images = [product_image]
            has_images = bool(product_images)
            # Support both old single id and new multi-select ids
            model_config_ids = data.get("model_config_ids") or []
            if not model_config_ids and data.get("model_config_id"):
                model_config_ids = [data["model_config_id"]]
            n_images = data.get("n", 1)
            # gpt-image-2 parameters
            quality = data.get("quality", "auto")
            size = data.get("size", "auto")

            if not prompt and not has_images:
                await websocket.send_json({"type": "error", "message": "请上传产品图片或输入描述"})
                continue

            if not prompt:
                prompt = "请分析这个产品"

            # Resolve image models (support multiple)
            image_models = []
            if model_config_ids:
                image_models = db.query(ModelConfig).filter(
                    ModelConfig.id.in_(model_config_ids), ModelConfig.owner_id == user_id
                ).all()
            if not image_models:
                # Fallback: all image models
                image_models = db.query(ModelConfig).filter(
                    ModelConfig.owner_id == user_id, ModelConfig.model_type == "image"
                ).all()

            image_cfgs = [
                {"api_key": m.api_key, "base_url": m.base_url, "model_name": m.model_name, "config_name": m.name}
                for m in image_models
            ]

            # Resolve a chat/text model used to expand one description into N
            # distinct prompts when multiple images are requested. Prefer the
            # user's default chat model, else the first chat model they have.
            text_cfg = None
            chat_models = db.query(ModelConfig).filter(
                ModelConfig.owner_id == user_id, ModelConfig.model_type == "chat"
            ).all()
            if chat_models:
                chosen = next((m for m in chat_models if m.is_default), chat_models[0])
                text_cfg = {
                    "api_key": chosen.api_key, "base_url": chosen.base_url,
                    "model_name": chosen.model_name, "config_name": chosen.name,
                }

            # Auto-set title
            existing = db.query(ImageTask).filter(ImageTask.conversation_id == conv_id).count()
            if existing == 0:
                conv.title = prompt[:50]
                db.commit()

            # Create task (store product images)
            uploaded_images_json = json.dumps({
                "product_image": product_images[0] if product_images else None,
                "product_images": product_images,
            }) if has_images else None
            task = ImageTask(
                conversation_id=conv_id,
                role="user",
                prompt=prompt,
                uploaded_image=product_images[0] if product_images else None,
                uploaded_images_json=uploaded_images_json,
                status="generating",
                owner_id=user_id,
                model_config_id=image_models[0].id if image_models else None,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id

            await websocket.send_json({
                "type": "task_created",
                "task": _task_dict(task),
            })

            # Resolve product image paths on disk (support multiple)
            product_paths = []
            for img_path in product_images:
                fname = img_path.split("/")[-1]
                product_paths.append(os.path.join(UPLOAD_DIR, fname))

            # Fallback to previous task if no current images
            if not product_paths:
                prev_task = (
                    db.query(ImageTask)
                    .filter(ImageTask.conversation_id == conv_id, ImageTask.id < task_id)
                    .order_by(ImageTask.created_at.desc())
                    .first()
                )
                if prev_task:
                    if prev_task.uploaded_images_json:
                        try:
                            prev_data = json.loads(prev_task.uploaded_images_json)
                            if isinstance(prev_data, dict):
                                # Try new multi-image field first
                                prev_imgs = prev_data.get("product_images") or []
                                if not prev_imgs and prev_data.get("product_image"):
                                    prev_imgs = [prev_data["product_image"]]
                                for p in prev_imgs:
                                    fname = p.split("/")[-1]
                                    product_paths.append(os.path.join(UPLOAD_DIR, fname))
                        except (json.JSONDecodeError, TypeError):
                            pass
                    elif prev_task.uploaded_image:
                        fname = prev_task.uploaded_image.split("/")[-1]
                        product_paths.append(os.path.join(UPLOAD_DIR, fname))

            # Release db session BEFORE long-running generation to prevent MySQL timeout
            db.close()

            # Stream generation (supports multiple image models)
            # Generation runs independently of WS - results are saved to DB
            # so even if WS disconnects, task will be updated in DB
            try:
                async for update in generate_image_stream(
                    prompt=prompt,
                    product_paths=product_paths if product_paths else None,
                    image_configs=image_cfgs if image_cfgs else None,
                    n=n_images,
                    text_config=text_cfg,
                    quality=quality,
                    size=size,
                ):
                    # Try to send progress via WS (ignore if disconnected)
                    try:
                        await websocket.send_json({"type": "progress", **update})
                    except Exception:
                        pass  # WS disconnected, but generation continues

                    if update.get("step") == "done":
                        result = update.get("result", {})
                        db = SessionLocal()
                        task = db.query(ImageTask).filter(ImageTask.id == task_id).first()
                        task.optimized_prompt = result.get("optimized_prompt")
                        # Store first image URL for backward compat
                        image_results = result.get("image_results", [])
                        if image_results:
                            first_ok = next((r for r in image_results if r.get("image_url")), None)
                            if first_ok:
                                task.result_image_url = first_ok["image_url"]
                            task.image_results_json = json.dumps(image_results, ensure_ascii=False)
                        elif result.get("image_url"):
                            task.result_image_url = result["image_url"]

                        # Determine status: failed if no successful images
                        has_success = any(r.get("image_url") for r in image_results) or result.get("image_url")
                        if not has_success:
                            task.status = "failed"
                            # Aggregate error messages from all models
                            errors = [r.get("error") for r in image_results if r.get("error")]
                            if errors:
                                task.error_msg = "; ".join(errors)
                            elif result.get("error"):
                                task.error_msg = result["error"]
                            else:
                                task.error_msg = "图片生成失败，未返回图片"
                        else:
                            task.status = "done"
                        db.commit()
                        db.refresh(task)
                        # Try to notify via WS (ignore if disconnected)
                        try:
                            await websocket.send_json({
                                "type": "task_updated",
                                "task": _task_dict(task),
                            })
                        except Exception:
                            pass  # WS disconnected, result saved to DB
                        db.close()
            except Exception as e:
                # Fresh db session to save error
                try:
                    db.close()
                except Exception:
                    pass
                db = SessionLocal()
                task = db.query(ImageTask).filter(ImageTask.id == task_id).first()
                if task:
                    task.status = "failed"
                    task.error_msg = str(e)
                    db.commit()
                    db.refresh(task)
                    try:
                        await websocket.send_json({
                            "type": "task_updated",
                            "task": _task_dict(task),
                        })
                    except Exception:
                        pass  # WS disconnected, error saved to DB
                db.close()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


def _task_dict(task: ImageTask) -> dict:
    image_results = None
    if task.image_results_json:
        try:
            image_results = json.loads(task.image_results_json)
        except (json.JSONDecodeError, TypeError):
            pass
    uploaded_images = None
    if task.uploaded_images_json:
        try:
            uploaded_images = json.loads(task.uploaded_images_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": task.id,
        "conversation_id": task.conversation_id,
        "role": task.role,
        "prompt": task.prompt,
        "uploaded_image": task.uploaded_image,
        "uploaded_images": uploaded_images,
        "optimized_prompt": task.optimized_prompt,
        "result_image_url": task.result_image_url,
        "image_results": image_results,
        "status": task.status,
        "error_msg": task.error_msg,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
