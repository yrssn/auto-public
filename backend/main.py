from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base
from routers.auth_router import router as auth_router
from routers.model_config_router import router as model_config_router
from routers.image_gen_router import router as image_gen_router

# Create tables
Base.metadata.create_all(bind=engine)

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


@app.get("/")
def root():
    return {"message": settings.APP_NAME}
