import asyncio
import logging
from fastapi import FastAPI
import uvicorn
from app.bot import bot, dp
from app.database import engine, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tinder Telegram Bot API")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up application...")
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Start bot polling in the background
    asyncio.create_task(dp.start_polling(bot))

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
