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
    global db_initialized
    if not db_initialized:
        await init_db()
        db_initialized = True

    """
    Webhook endpoint for Telegram.
    Receives JSON updates from Telegram and feeds them to the aiogram dispatcher.
    """
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
    return {"status": "ok"}
