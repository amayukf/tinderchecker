import os
from fastapi import FastAPI, Request, Response
from aiogram import types
from app.bot import dp, bot, init_db
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Global variable to track DB initialization
db_initialized = False

WEBHOOK_PATH = f"/api/webhook"

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    """
    Webhook endpoint for Telegram.
    Receives JSON updates from Telegram and feeds them to the aiogram dispatcher.
    """
    global db_initialized
    if not db_initialized:
        try:
            await init_db()
            db_initialized = True
        except Exception as e:
            logging.error(f"Database initialization failed: {e}")
            # We don't return 500 yet, maybe it works anyway if tables exist

    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        await dp.feed_update(bot=bot, update=update)
        return Response(status_code=200)
    except Exception as e:
        logging.error(f"Error processing update: {e}")
        return Response(status_code=500)

@app.get("/")
async def root():
    return {"message": "Tinder Telegram Bot is running on Vercel!"}

@app.get("/api/health")
async def health():
    from app.config import settings
    from app.database import engine
    from sqlalchemy import text
    
    db_status = "unknown"
    db_error = None
    
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception as e:
        db_status = "failed"
        db_error = str(e)
        
    return {
        "status": "ok",
        "bot_token": settings.TELEGRAM_BOT_TOKEN[:5] + "...",
        "database": {
            "status": db_status,
            "url_masked": settings.DATABASE_URL.split("@")[-1],
            "error": db_error
        },
        "vercel": os.environ.get("VERCEL")
    }
