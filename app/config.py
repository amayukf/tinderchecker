import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./tinder_bot.db")
    REDIS_URL: str = "redis://redis:6379/0"
    ENVIRONMENT: str = "production"
    OWNER_ID: int | None = None
    TINDER_AUTH_TOKEN: str | None = None

    class Config:
        env_file = ".env"
        extra = "allow"

    def __init__(self, **values):
        super().__init__(**values)
        if os.getenv("VERCEL") and "sqlite" in self.DATABASE_URL:
            self.DATABASE_URL = "sqlite+aiosqlite:////tmp/tinder_bot.db"

settings = Settings()
