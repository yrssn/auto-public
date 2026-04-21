from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    model_configs = relationship("ModelConfig", back_populates="owner")
    conversations = relationship("Conversation", back_populates="owner")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, default="新会话")
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="conversations")
    tasks = relationship("ImageTask", back_populates="conversation", order_by="ImageTask.created_at")


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)  # openai / deepseek / zhipu / etc.
    model_name = Column(String(100), nullable=False)
    api_key = Column(String(255), nullable=False)
    base_url = Column(String(255), nullable=True)
    model_type = Column(String(20), default="chat")  # chat / image
    is_default = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="model_configs")


class ImageTask(Base):
    __tablename__ = "image_tasks"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), default="user")  # user / assistant
    prompt = Column(Text, nullable=False)
    uploaded_image = Column(String(500), nullable=True)
    optimized_prompt = Column(Text, nullable=True)
    result_image_url = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")  # pending / generating / done / failed
    error_msg = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    model_config_id = Column(Integer, ForeignKey("model_configs.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="tasks")
