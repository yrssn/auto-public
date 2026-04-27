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
            # Scene images (backgrounds/templates) and product image (subject)
            scene_images = data.get("scene_images") or []
            product_image = data.get("product_image")
            # Backward compat: old uploaded_images format
            if not scene_images and not product_image:
                uploaded_images = data.get("uploaded_images") or []
                if not uploaded_images and data.get("uploaded_image"):
                    uploaded_images = [data["uploaded_image"]]
                scene_images = uploaded_images
            
            has_images = bool(scene_images or product_image)
            # Support both old single id and new multi-select ids
            model_config_ids = data.get("model_config_ids") or []
            if not model_config_ids and data.get("model_config_id"):
                model_config_ids = [data["model_config_id"]]
            optimize = data.get("optimize_prompt", True)
            n_images = data.get("n", 1)

            if not prompt and not has_images:
                await websocket.send_json({"type": "error", "message": "请输入描述或上传图片"})
                continue

            if not prompt:
                if product_image and scene_images:
                    prompt = "将产品图中的商品替换到这些场景图中"
                elif scene_images:
                    prompt = "请分析这些场景图片"
                else:
                    prompt = "请分析这个产品"

            # Resolve prompt optimization model
            if has_images and optimize:
                prompt_model = db.query(ModelConfig).filter(
                    ModelConfig.owner_id == user_id, ModelConfig.model_type == "vision"
                ).first()
                if not prompt_model:
                    prompt_model = db.query(ModelConfig).filter(
                        ModelConfig.owner_id == user_id, ModelConfig.model_type == "chat"
                    ).first()
            else:
                prompt_model = db.query(ModelConfig).filter(
                    ModelConfig.owner_id == user_id, ModelConfig.model_type == "chat"
                ).first()

            if not prompt_model:
                prompt_model = db.query(ModelConfig).filter(
                    ModelConfig.owner_id == user_id, ModelConfig.is_default == True
                ).first()
            if not prompt_model:
                await websocket.send_json({"type": "error", "message": "请先配置聊天模型或视觉模型（用于优化提示词）"})
                continue

            chat_model = prompt_model

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

            chat_cfg = {"api_key": chat_model.api_key, "base_url": chat_model.base_url, "model_name": chat_model.model_name}
            image_cfgs = [
                {"api_key": m.api_key, "base_url": m.base_url, "model_name": m.model_name, "config_name": m.name}
                for m in image_models
            ]

            # Auto-set title
            existing = db.query(ImageTask).filter(ImageTask.conversation_id == conv_id).count()
            if existing == 0:
                conv.title = prompt[:50]
                db.commit()

            # Create task (store scene and product images)
            all_images = scene_images + ([product_image] if product_image else [])
            uploaded_images_json = json.dumps({
                "scene_images": scene_images,
                "product_image": product_image,
            }) if has_images else None
            task = ImageTask(
                conversation_id=conv_id,
                role="user",
                prompt=prompt,
                uploaded_image=all_images[0] if all_images else None,
                uploaded_images_json=uploaded_images_json,
                status="generating",
                owner_id=user_id,
                model_config_id=image_models[0].id if image_models else chat_model.id,
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

            # Resolve image paths on disk
            scene_paths = []
            product_path = None
            if scene_images:
                for img_url in scene_images:
                    fname = img_url.split("/")[-1]
                    scene_paths.append(os.path.join(UPLOAD_DIR, fname))
            if product_image:
                fname = product_image.split("/")[-1]
                product_path = os.path.join(UPLOAD_DIR, fname)
            
            # Fallback to previous task if no current images
            if not scene_paths and not product_path:
                prev_task = (
                    db.query(ImageTask)
                    .filter(ImageTask.conversation_id == conv_id, ImageTask.id < task_id)
                    .order_by(ImageTask.created_at.desc())
                    .first()
                )
                if prev_task:
                    if prev_task.result_image_url:
                        scene_paths = [prev_task.result_image_url]
                    elif prev_task.uploaded_images_json:
                        try:
                            prev_data = json.loads(prev_task.uploaded_images_json)
                            if isinstance(prev_data, dict):
                                for img_url in prev_data.get("scene_images", []):
                                    fname = img_url.split("/")[-1]
                                    scene_paths.append(os.path.join(UPLOAD_DIR, fname))
                                if prev_data.get("product_image"):
                                    fname = prev_data["product_image"].split("/")[-1]
                                    product_path = os.path.join(UPLOAD_DIR, fname)
                            else:
                                # Old format: list of images
                                for img_url in prev_data:
                                    fname = img_url.split("/")[-1]
                                    scene_paths.append(os.path.join(UPLOAD_DIR, fname))
                        except (json.JSONDecodeError, TypeError):
                            pass
                    elif prev_task.uploaded_image:
                        fname = prev_task.uploaded_image.split("/")[-1]
                        scene_paths = [os.path.join(UPLOAD_DIR, fname)]

            # Stream generation (supports multiple image models)
            try:
                async for update in generate_image_stream(
                    prompt=prompt,
                    optimize=optimize,
                    scene_paths=scene_paths,
                    product_path=product_path,
                    chat_config=chat_cfg,
                    image_configs=image_cfgs if image_cfgs else None,
                    history=history,
                    n=n_images,
                ):
                    await websocket.send_json({"type": "progress", **update})

                    if update.get("step") == "done":
                        result = update.get("result", {})
                        db.rollback()
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

                        if result.get("error") and not image_results:
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
