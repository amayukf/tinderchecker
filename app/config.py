import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./tinder_bot.db")
    REDIS_URL: str = "redis://redis:6379/0"
    ENVIRONMENT: str = "production"
    OWNER_ID: str | None = None
    TINDER_AUTH_TOKEN: str | None = None

    class Config:
        env_file = ".env"
        extra = "allow"

    def __init__(self, **values):
        super().__init__(**values)
        url = self.DATABASE_URL
        
        # 1. Neon/Supabase Fix (convert postgres:// to postgresql+asyncpg://)
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
        # 2. Heavy Sanitization: Remove query parameters like ?sslmode=...
        # asyncpg doesn't support these in the URL string
        if "+asyncpg://" in url and "?" in url:
            url = url.split("?")[0]

        # 3. Vercel SQLite Fix (use /tmp if using default sqlite)
        if os.getenv("VERCEL") and "sqlite" in url and "./" in url:
            url = "sqlite+aiosqlite:////tmp/tinder_bot.db"
            
        self.DATABASE_URL = url

settings = Settings()
