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
    image_tasks = relationship("ImageTask", back_populates="owner")


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)  # openai / deepseek / zhipu / etc.
    model_name = Column(String(100), nullable=False)
    api_key = Column(String(255), nullable=False)
    base_url = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="model_configs")


class ImageTask(Base):
    __tablename__ = "image_tasks"

    id = Column(Integer, primary_key=True, index=True)
    prompt = Column(Text, nullable=False)
    optimized_prompt = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")  # pending / generating / done / failed
    error_msg = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    model_config_id = Column(Integer, ForeignKey("model_configs.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="image_tasks")
