import os
import time
import asyncio
import logging
import html
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from app.config import settings
from app.tinder_client import TinderClient
from app.database import AsyncSessionLocal, engine, Base
from app.models import User, QueryLog
from sqlalchemy import select, func, update, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
tinder_client = TinderClient()

user_rate_limit = {}
RATE_LIMIT_SECONDS = 5

from sqlalchemy import text

async def init_db():
    """Initializes the database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized.")

async def register_user(tg_user: types.User):
    """Saves or updates user info in the database (Background task safe)."""
    if not tg_user:
        return
    try:
        async with AsyncSessionLocal() as session:
            user_values = {
                'user_id': tg_user.id,
                'username': tg_user.username,
                'full_name': tg_user.full_name
            }
            if "postgresql" in engine.dialect.name:
                stmt = pg_insert(User).values(**user_values).on_conflict_do_update(
                    index_elements=['user_id'],
                    set_={'username': tg_user.username, 'full_name': tg_user.full_name}
                )
            else:
                stmt = sqlite_insert(User).values(**user_values).on_conflict_do_update(
                    index_elements=['user_id'],
                    set_={'username': tg_user.username, 'full_name': tg_user.full_name}
                )
            await session.execute(stmt)
            await session.commit()
    except Exception as e:
        logger.error(f"register_user failed: {e}")

async def log_query(user_id: int, query: str, status: str):
    """Logs a query to the database (Background task safe)."""
    try:
        async with AsyncSessionLocal() as session:
            log = QueryLog(user_id=user_id, username_or_url=query, status=status)
            session.add(log)
            await session.commit()
    except Exception as e:
        logger.error(f"log_query failed: {e}")

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    try:
        await register_user(message.from_user)
    except Exception as e:
        logger.error(f"register_user in cmd_start failed: {e}")
    welcome_text = (
        f"🔍 <b>[Tinder Analysis Service]</b>\n\n"
        f"Welcome to the ultimate Tinder OSINT & profile verification platform!\n\n"
        f"⚡ <b>Core Features:</b>\n"
        f"• Accurate Account Status (Active / Limited)\n"
        f"• Real-time Verification & Photo Counts\n"
        f"• Account Creation & ID Statistics\n\n"
        f"👉 <b>How to Use:</b>\n"
        f"Simply send any Tinder profile link or username to begin:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Join", url="https://t.me/N_Notic")]])
    await message.answer(welcome_text, reply_markup=keyboard, disable_web_page_preview=True)

@dp.message(Command("debug"))
async def cmd_debug(message: types.Message):
    """Owner-only diagnostic command."""
    if str(message.from_user.id) != str(settings.OWNER_ID):
        return
    try:
        is_owner = str(message.from_user.id) == str(settings.OWNER_ID)
        status = "✅ Owner" if is_owner else "❌ User"
        await message.answer(
            f"🛠️ <b>Debug Info:</b>\n"
            f"• Your ID: <code>{message.from_user.id}</code>\n"
            f"• Owner ID in config: <code>{settings.OWNER_ID}</code>\n"
            f"• Match: {status}"
        )
    except Exception as e:
        logger.error(f"cmd_debug error: {e}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Owner-only stats command."""
    if str(message.from_user.id) != str(settings.OWNER_ID):
        return
    try:
        async with AsyncSessionLocal() as session:
            user_count = await session.scalar(select(func.count(User.id)))
            query_count = await session.scalar(select(func.count(QueryLog.id)))
        await message.answer(f"📊 <b>Bot Statistics:</b>\n\n• Total Users: <code>{user_count}</code>\n• Total Queries: <code>{query_count}</code>")
    except Exception as e:
        await message.answer(f"❌ DB Error: {html.escape(str(e))}")

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    """Owner-only users list command."""
    if str(message.from_user.id) != str(settings.OWNER_ID):
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).order_by(User.id.desc()).limit(50)
        )
        users = result.scalars().all()
        
    if not users:
        await message.answer("📝 No users registered yet.")
        return
        
    try:
        user_list = "👥 <b>Recent Registered Users:</b>\n\n"
        for i, user in enumerate(users, 1):
            name_clean = html.escape(user.full_name or "Unknown")
            user_clean = html.escape(user.username or "No Username")
            user_line = f"{i}. {name_clean} (@{user_clean})\n"
            if len(user_list) + len(user_line) > 4000:
                break
            user_list += user_line
        await message.answer(user_list)
    except Exception as e:
        await message.answer(f"❌ Error building list: {html.escape(str(e))}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    """Owner-only broadcast command."""
    if str(message.from_user.id) != str(settings.OWNER_ID):
        return

    broadcast_msg = message.text.replace("/broadcast", "", 1).strip()
    reply_msg = message.reply_to_message
    
    if not broadcast_msg and not reply_msg:
        await message.answer("⚠️ Please provide a message or reply to a message to broadcast.")
        return

    status_msg = await message.answer("📢 <b>Starting broadcast...</b>")
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.user_id))
        user_ids = [row[0] for row in result.all()]
    
    success = success_count = 0
    failed = 0
    
    for uid in user_ids:
        try:
            if reply_msg:
                await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=reply_msg.message_id)
            else:
                await bot.send_message(chat_id=uid, text=broadcast_msg)
            success_count += 1
            await asyncio.sleep(0.05) # Avoid flood limits
        except Exception:
            failed += 1
    
    await status_msg.edit_text(
        f"✅ <b>Broadcast Finished!</b>\n\n"
        f"• Targeted: {len(user_ids)}\n"
        f"• Success: {success_count}\n"
        f"• Failed: {failed}"
    )

@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return

    await register_user(message.from_user)
    user_id = message.from_user.id
    
    # Rate Limiting
    current_time = time.time()
    if user_id in user_rate_limit and current_time - user_rate_limit[user_id] < RATE_LIMIT_SECONDS:
        remaining = int(RATE_LIMIT_SECONDS - (current_time - user_rate_limit[user_id]))
        await message.answer(f"⏳ Please wait {remaining} seconds before sending another request.")
        return
        
    user_rate_limit[user_id] = current_time
    input_text = message.text

    username = tinder_client.extract_username(input_text)
    if not username:
        await message.answer("❌ Invalid format. Please send a valid Tinder URL or username.")
        return

    msg = await message.answer(f"🔍 Analyzing profile for <b>{html.escape(username)}</b>...")
    
    data = await tinder_client.get_profile_data(username)
    
    if data["status"] == "not_found":
        await log_query(user_id, username, "not_found")
        await msg.edit_text(f"❌ Profile not active")
        # Log failure to owner
        if settings.OWNER_ID and str(user_id) != str(settings.OWNER_ID):
            try:
                user = message.from_user
                name_clean = html.escape(user.full_name or "Unknown")
                user_clean = html.escape(user.username or "No Username")
                is_premium = "👑 Yes" if user.is_premium else "❌ No"
                log_text = (
                    f"📊 <b>Bot Query (Inactive Profile)</b>\n\n"
                    f"• <b>User:</b> <a href='tg://user?id={user.id}'>{name_clean}</a>\n"
                    f"• <b>Username:</b> @{user_clean}\n"
                    f"• <b>User ID:</b> <code>{user.id}</code>\n"
                    f"• <b>Language:</b> 🌐 <code>{html.escape(user.language_code or 'Unknown')}</code>\n"
                    f"• <b>Telegram Premium:</b> {is_premium}\n"
                    f"• <b>Queried Profile:</b> @{html.escape(username)}\n"
                    f"• <b>Status:</b> ❌ Profile not active"
                )
                await bot.send_message(chat_id=settings.OWNER_ID, text=log_text)
            except Exception:
                pass
        return
    elif data["status"] == "error":
        await log_query(user_id, username, "error")
        await msg.edit_text("⚠️ An error occurred while fetching the profile. Please try again later.")
        return
    
    await log_query(user_id, username, "success")
        
    bot_info = await bot.get_me()
    
    if data.get("is_restricted"):
        report = (
            f"⚠️ <b>Account Limited</b>\n\n"
            f"👤 <b>Username:</b> @{html.escape(username)}\n"
            f"⚠️ <b>Status:</b> Limited Account\n\n"
            f"⚠️ <b>This account has restricted functionality</b>"
        )
    else:
        status_str = "✅ ACTIVE ACCOUNT"
        verified_str = "👑 Verified Profile" if data.get("verified") else "❌ Not Verified"
        
        report = (
            f"🔍 <b>[Tinder Analysis Bot]</b>\n\n"
            f"• Account Status: {status_str}\n"
            f"• Verification: {verified_str}\n"
            f"• Username: @{html.escape(username)}\n"
            f"• Display Name: {html.escape(data.get('name') or 'N/A')}\n"
            f"• User Age: {data.get('age') or 'Unknown'} years\n"
            f"• Birth Date: {html.escape(data.get('birth_date') or 'Hidden')}\n"
            f"• Job/Work: {html.escape(data.get('jobs') or 'Not Specified')}\n"
            f"• School/Uni: {html.escape(data.get('schools') or 'Not Specified')}\n"
            f"• Total Photos: 📸 {data.get('photos_count') or 'Unknown'} upload(s)\n"
            f"• Bio: <i>\"{html.escape(data.get('bio') or 'No bio written.')}\"</i>\n\n"
            f"• Account Age: {html.escape(data.get('account_age') or 'Unknown')}\n"
            f"• Registration Time: {html.escape(data.get('creation_date') or 'Unknown')}\n"
            f"• Account ID: <code>{html.escape(data.get('account_id') or 'Unknown')}</code>\n\n"
            f"Official Link: https://tinder.com/@{html.escape(username)}\n\n"
            f"🤖 Bot: https://t.me/{bot_info.username}"
        )
    
    await msg.delete()
    
    if data.get("is_restricted"):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Join", url="https://t.me/N_Notic")]
        ])
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Sell This Account", url="https://t.me/T_ump")],
            [InlineKeyboardButton(text="📢 Join", url="https://t.me/N_Notic")]
        ])
    
    # Log success to owner (Only if not owner themselves)
    if settings.OWNER_ID and str(user_id) != str(settings.OWNER_ID):
        try:
            user = message.from_user
            name_clean = html.escape(user.full_name or "Unknown")
            user_clean = html.escape(user.username or "No Username")
            is_premium = "👑 Yes" if user.is_premium else "❌ No"
            status_log = "⚠️ Limited Account" if data.get("is_restricted") else "✅ Active Account"
            log_text = (
                f"📊 <b>New Bot Query (Success)!</b>\n\n"
                f"• <b>User:</b> <a href='tg://user?id={user.id}'>{name_clean}</a>\n"
                f"• <b>Username:</b> @{user_clean}\n"
                f"• <b>User ID:</b> <code>{user.id}</code>\n"
                f"• <b>Language:</b> 🌐 <code>{html.escape(user.language_code or 'Unknown')}</code>\n"
                f"• <b>Telegram Premium:</b> {is_premium}\n"
                f"• <b>Queried Profile:</b> @{html.escape(username)}\n"
                f"• <b>Tinder Token Status:</b> ⚙️ <code>{data.get('token_status') or 'Unknown'}</code>\n"
                f"• <b>Status:</b> {status_log}"
            )
            await bot.send_message(chat_id=settings.OWNER_ID, text=log_text)
        except Exception:
            pass
            
    if data.get("image_url"):
        try:
            await message.answer_photo(photo=data["image_url"], caption=report, reply_markup=keyboard)
        except Exception:
            await message.answer(report, disable_web_page_preview=True, reply_markup=keyboard)
    else:
        await message.answer(report, disable_web_page_preview=True, reply_markup=keyboard)
