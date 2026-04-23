from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "电商选品系统"
    DATABASE_URL: str = "sqlite:///./app.db"
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    ZINIAO_APP_ID: str = ""
    ZINIAO_APP_SECRET: str = ""
    ZINIAO_API_URL: str = "https://sbappstoreapi.ziniao.com"

    class Config:
        env_file = ".env"


settings = Settings()
