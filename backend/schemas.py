from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


# ---- Auth ----
class UserCreate(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Model Config ----
class ModelConfigCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = None
    model_type: str = "chat"  # chat / image
    is_default: bool = False


class ModelConfigUpdate(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: Optional[str] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_type: Optional[str] = None
    is_default: Optional[bool] = None


class ModelConfigOut(BaseModel):
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: int
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = None
    model_type: str = "chat"
    is_default: bool
    created_at: datetime


# ---- Image Generation ----
class ImageTaskOut(BaseModel):
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: int
    conversation_id: int
    role: str
    prompt: str
    uploaded_image: Optional[str] = None
    uploaded_images: Optional[Any] = None
    optimized_prompt: Optional[str] = None
    result_image_url: Optional[str] = None
    image_results: Optional[list] = None
    status: str
    error_msg: Optional[str] = None
    created_at: datetime


# ---- Conversation ----
class ConversationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    tasks: list[ImageTaskOut] = []
