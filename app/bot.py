import os
import re
import time
import asyncio
import logging
import html
import datetime
import io
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
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

# ── Formatting helpers ────────────────────────────────────────────
def _fmt_date(date_str: str) -> str:
    """'2025-07-25 12:14:51 UTC' → '25 Jul 2025'"""
    try:
        d = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
        return f"{d.day} {d.strftime('%b %Y')}"
    except Exception:
        return date_str or "Unknown"

def _fmt_age(age_str: str) -> str:
    """'2y 3m 14d' → '2 Years 3 Months 14 Days'"""
    if not age_str or age_str == "Unknown":
        return "Unknown"
    parts = []
    for pat, s, p in [(r'(\d+)y','Year','Years'),(r'(\d+)m','Month','Months'),(r'(\d+)d','Day','Days')]:
        m = re.search(pat, age_str)
        if m:
            n = int(m.group(1))
            parts.append(f"{n} {s if n == 1 else p}")
    return " ".join(parts) if parts else age_str

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
        if settings.admin_list:
            try:
                primary_owner = settings.admin_list[0]
                error_clean = html.escape(str(e))
                await bot.send_message(primary_owner, f"❌ <b>Database Error (register_user):</b>\n<code>{error_clean}</code>")
            except Exception: pass

async def log_query(user_id: int, query: str, status: str):
    """Logs a query to the database (Background task safe)."""
    try:
        async with AsyncSessionLocal() as session:
            log = QueryLog(user_id=user_id, username_or_url=query, status=status)
            session.add(log)
            await session.commit()
    except Exception as e:
        logger.error(f"log_query failed: {e}")
        if settings.admin_list:
            try:
                primary_owner = settings.admin_list[0]
                error_clean = html.escape(str(e))
                await bot.send_message(primary_owner, f"❌ <b>Database Error (log_query):</b>\n<code>{error_clean}</code>")
            except Exception: pass

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    try:
        await register_user(message.from_user)
    except Exception as e:
        logger.error(f"register_user in cmd_start failed: {e}")
    welcome_text = (
        f"🔥 <b>Welcome to Premium Tinder Checker!</b> 🔥\n\n"
        f"🎯 Send me any Tinder username to check.\n\n"
        f"<i>Examples:</i>\n"
        f"• boy\n"
        f"• @boy\n"
        f"• tinder.com/@boy"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Join Channel", url="https://t.me/N_Notic")]])
    await message.answer(welcome_text, reply_markup=keyboard, disable_web_page_preview=True)

@dp.message(Command("debug"))
async def cmd_debug(message: types.Message):
    """Owner-only diagnostic command."""
    if str(message.from_user.id) not in settings.admin_list:
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
    if str(message.from_user.id) not in settings.admin_list:
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
    if str(message.from_user.id) not in settings.admin_list:
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).order_by(User.id.asc()) # Ascending to show oldest first in file
        )
        users = result.scalars().all()
        
    if not users:
        await message.answer("📝 No users registered yet.")
        return
        
    try:
        # Build text for file
        file_content = "👥 TINDER BOT REGISTERED USERS\n" + "="*30 + "\n\n"
        for i, user in enumerate(users, 1):
            name = user.full_name or "Unknown"
            username = user.username or "No Username"
            file_content += f"{i}. {name} (@{username}) | ID: {user.user_id}\n"
            
        # Send as document to avoid message character limits
        text_file = BufferedInputFile(file_content.encode("utf-8"), filename="users_list.txt")
        await message.answer_document(
            document=text_file, 
            caption=f"✅ <b>Total Users Found:</b> <code>{len(users)}</code>\n\nFull user list generated successfully."
        )
    except Exception as e:
        await message.answer(f"❌ Error exporting list: {html.escape(str(e))}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    """Owner-only broadcast command."""
    if str(message.from_user.id) not in settings.admin_list:
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
    
    SEP = "═══════════════════════════════════════"
    
    if data["status"] == "not_found" or data.get("is_restricted"):
        status_text = "❌ BANNED / DELETED" if data.get("is_restricted") else "❌ BANNED / DELETED"
        report = (
            f"{SEP}\n"
            f"💣 Tinder DNA Analysis Result 💥\n"
            f"{SEP}\n\n"
            f"🔴 Account: <code>{status_text}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Username: <code>@{html.escape(username)}</code>\n\n"
            f"{SEP}\n"
            f"✅ Analysis Complete\n"
            f"{SEP}"
        )
        await log_query(user_id, username, "not_found")
        await msg.delete()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Join Channel", url="https://t.me/N_Notic")]
        ])
        await message.answer(report, reply_markup=keyboard)
        # Log failure to owner
        if settings.admin_list and str(user_id) not in settings.admin_list:
            try:
                primary_owner = settings.admin_list[0]
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
                    f"• <b>Status:</b> ❌ Profile not active/Banned"
                )
                await bot.send_message(chat_id=primary_owner, text=log_text)
            except Exception:
                pass
        return
    elif data["status"] == "error":
        await log_query(user_id, username, "error")
        await msg.edit_text("⚠️ An error occurred while fetching the profile. Please try again later.")
        return
    
    await log_query(user_id, username, "success")
    
    reg_year = ""
    creation_date_val = data.get('creation_date') or ""
    if creation_date_val and creation_date_val != "Hidden":
        reg_year = creation_date_val[:4]

    photos = data.get('photos_count') or '0'
    age = data.get('age') or 'Unknown'
    name = html.escape(data.get('name') or 'Hidden')
    birth_date = html.escape(data.get('birth_date') or 'Hidden')
    account_age = html.escape(data.get('account_age') or 'Unknown')

    report = (
        f"{SEP}\n"
        f"🔥 Tinder DNA Analysis Result ✨\n"
        f"{SEP}\n\n"
        f"🟢 Account: Active Account\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 Username: <code>@{html.escape(username)}</code>\n"
        f"👤 Display Name: {name}\n"
        f"📅 Birth Date: {birth_date}\n"
        f"🎂 User Age: {age} years\n"
        f"📸 Photos: {photos}\n"
        f"⏳ Account Age: {account_age}\n"
        f"� Created Time: {html.escape(creation_date_val or 'Unknown')}\n"
        f"✅ Verification: ❌ Not Verified\n\n"
        f"{SEP}\n"
        f"✅ Analysis Complete\n"
        f"{SEP}"
    )

    await msg.delete()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="� Sell This Account", url="https://t.me/T_ump"), InlineKeyboardButton(text="📢 Join Channel", url="https://t.me/N_Notic")]
    ])
    
    # Log success to owner (Only if not an admin themselves)
    if settings.admin_list and str(user_id) not in settings.admin_list:
        try:
            primary_owner = settings.admin_list[0]
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
            await bot.send_message(chat_id=primary_owner, text=log_text)
        except Exception:
            pass
            
    if data.get("image_url"):
        try:
            await message.answer_photo(photo=data["image_url"], caption=report, reply_markup=keyboard)
        except Exception:
            await message.answer(report, disable_web_page_preview=True, reply_markup=keyboard)
    else:
        await message.answer(report, disable_web_page_preview=True, reply_markup=keyboard)
