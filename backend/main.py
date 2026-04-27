import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text
from config import settings
from database import engine, Base
from routers.auth_router import router as auth_router
from routers.model_config_router import router as model_config_router
from routers.image_gen_router import router as image_gen_router
from routers.ziniao_router import router as ziniao_router
from routers.product_selection_router import router as product_selection_router

# Create tables
Base.metadata.create_all(bind=engine)

# Auto-migrate: add missing columns
def run_migrations():
    migrations = [
        ("image_tasks", "uploaded_images_json", "ALTER TABLE image_tasks ADD COLUMN uploaded_images_json TEXT NULL AFTER uploaded_image"),
    ]
    with engine.connect() as conn:
        for table, column, sql in migrations:
            result = conn.execute(text(f"SHOW COLUMNS FROM {table} LIKE '{column}'"))
            if not result.fetchone():
                print(f"[Migration] Adding column {table}.{column}")
                conn.execute(text(sql))
                conn.commit()

try:
    run_migrations()
except Exception as e:
    print(f"[Migration] Skipped: {e}")

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
app.include_router(product_selection_router)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def root():
    return {"message": settings.APP_NAME}
