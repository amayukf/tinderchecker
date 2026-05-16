import os
from fastapi import FastAPI, Request, Response
from aiogram import types
from app.bot import dp, bot
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI()

WEBHOOK_PATH = f"/api/webhook"

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
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
