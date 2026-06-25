from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DEBUG: bool = False
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str
    ADMIN_EMAIL: str = "admin@example.com"

    class Config:
        env_file = ".env"

settings = Settings()
