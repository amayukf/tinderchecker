import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./tinder_bot.db"
    REDIS_URL: str = "redis://redis:6379/0"  # For rate limiting or cache if needed
    ENVIRONMENT: str = "production"
    OWNER_ID: int | None = None

    class Config:
        env_file = ".env"

settings = Settings()
