from pydantic import BaseModel
from typing import Optional
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
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = None
    is_default: bool = False


class ModelConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_default: Optional[bool] = None


class ModelConfigOut(BaseModel):
    id: int
    name: str
    provider: str
    model_name: str
    api_key: str
    base_url: Optional[str] = None
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Image Generation ----
class ImageGenRequest(BaseModel):
    prompt: str
    model_config_id: Optional[int] = None
    optimize_prompt: bool = True


class ImageTaskOut(BaseModel):
    id: int
    prompt: str
    optimized_prompt: Optional[str] = None
    image_url: Optional[str] = None
    status: str
    error_msg: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
