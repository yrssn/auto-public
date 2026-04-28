from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "电商选品系统"
    DATABASE_URL: str = "mysql+pymysql://root:Aut0Pub!ic_2024#Mx@localhost:13306/auto_public?charset=utf8mb4"
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    ZINIAO_APP_ID: str = ""
    ZINIAO_APP_SECRET: str = ""
    ZINIAO_API_URL: str = "https://sbappstoreapi.ziniao.com"

    AOXIA_ACCESS_KEY: str = ""
    AOXIA_SECRET_KEY: str = ""
    AOXIA_MCP_BASE_URL: str = "https://mcp.alphashop.cn"

    class Config:
        env_file = ".env"


settings = Settings()
