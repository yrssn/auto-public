import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import engine, Base
from routers.auth_router import router as auth_router
from routers.model_config_router import router as model_config_router
from routers.image_gen_router import router as image_gen_router
from routers.ziniao_router import router as ziniao_router

# Create tables
Base.metadata.create_all(bind=engine)

# Auto-migrate: add missing columns
from sqlalchemy import inspect, text
with engine.connect() as conn:
    inspector = inspect(engine)
    if 'ziniao_accounts' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('ziniao_accounts')]
        if 'user_code' not in columns:
            conn.execute(text("ALTER TABLE ziniao_accounts ADD COLUMN user_code VARCHAR(255)"))
            conn.commit()

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(model_config_router)
app.include_router(image_gen_router)
app.include_router(ziniao_router)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def root():
    return {"message": settings.APP_NAME}
