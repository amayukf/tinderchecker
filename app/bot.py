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
from aiogram.enums import ParseMode, ChatMemberStatus
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

REQUIRED_CHANNEL = "@N_Notic"
CHANNEL_URL = "https://t.me/N_Notic"

async def init_db():
    """Initializes the database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add new columns if they don't exist (migration-safe)
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN referred_by BIGINT"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0"))
        except Exception:
            pass
    logger.info("Database initialized.")

async def check_channel_membership(user_id: int) -> bool:
    """Check if a user is a member of the required channel."""
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]
    except Exception as e:
        logger.error(f"Channel membership check failed: {e}")
        return False

async def send_join_prompt(message: types.Message):
    """Send a message requiring the user to join the channel first."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join Channel", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ I've Joined", callback_data="check_joined")]
    ])
    await message.answer(
        f"🔒 <b>Channel Membership Required!</b>\n\n"
        f"To use this bot, you must first join our channel:\n"
        f"👉 {CHANNEL_URL}\n\n"
        f"After joining, tap <b>✅ I've Joined</b> below.",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(lambda c: c.data == "check_joined")
async def callback_check_joined(callback: types.CallbackQuery):
    """Handle the 'I've Joined' button press."""
    is_member = await check_channel_membership(callback.from_user.id)
    if is_member:
        await callback.message.edit_text(
            f"✅ <b>Verified!</b> You are now a member.\n\n"
            f"🔥 Send me any Tinder username to start checking profiles!"
        )
        await callback.answer("✅ Verified! You can now use the bot.", show_alert=False)
    else:
        await callback.answer("❌ You haven't joined yet! Please join the channel first.", show_alert=True)

async def register_user(tg_user: types.User, referred_by: int = None):
    """Saves or updates user info in the database (Background task safe)."""
    if not tg_user:
        return
    try:
        async with AsyncSessionLocal() as session:
            # Check if user already exists
            existing = await session.scalar(select(User.id).where(User.user_id == tg_user.id))
            
            if existing:
                # Update existing user (don't overwrite referral info)
                await session.execute(
                    update(User).where(User.user_id == tg_user.id).values(
                        username=tg_user.username,
                        full_name=tg_user.full_name
                    )
                )
            else:
                # New user - insert with referral info
                new_user = User(
                    user_id=tg_user.id,
                    username=tg_user.username,
                    full_name=tg_user.full_name,
                    referred_by=referred_by,
                    referral_count=0
                )
                session.add(new_user)
                
                # Credit the referrer
                if referred_by and referred_by != tg_user.id:
                    await session.execute(
                        update(User).where(User.user_id == referred_by).values(
                            referral_count=User.referral_count + 1
                        )
                    )
                    # Notify the referrer
                    try:
                        await bot.send_message(
                            chat_id=referred_by,
                            text=(
                                f"🎉 <b>New Referral!</b>\n\n"
                                f"<a href='tg://user?id={tg_user.id}'>{html.escape(tg_user.full_name or 'Someone')}</a> "
                                f"joined using your referral link!\n"
                                f"Use /refer to see your total referrals."
                            )
                        )
                    except Exception:
                        pass
            
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
    # Extract referral ID from deep link (e.g., /start ref_12345678)
    referrer_id = None
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
        except ValueError:
            pass
    
    try:
        await register_user(message.from_user, referred_by=referrer_id)
    except Exception as e:
        logger.error(f"register_user in cmd_start failed: {e}")
    
    # Check channel membership
    is_member = await check_channel_membership(message.from_user.id)
    if not is_member:
        await send_join_prompt(message)
        return
    
    # Get bot info for referral link
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    
    welcome_text = (
        f"🔥 <b>Welcome to Premium Tinder OSINT & DNA Checker!</b> 🔥\n\n"
        f"🎯 Send me any Tinder username to inspect status, account age & OSINT risk score.\n\n"
        f"<i>Examples:</i>\n"
        f"• boy\n"
        f"• @boy\n"
        f"• tinder.com/@boy\n\n"
        f"📎 <b>Your Referral Link:</b>\n<code>{referral_link}</code>\n"
        f"Share it & earn referral credits!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join Channel", url=CHANNEL_URL)]
    ])
    await message.answer(welcome_text, reply_markup=keyboard, disable_web_page_preview=True)

@dp.message(Command("refer"))
async def cmd_refer(message: types.Message):
    """Show user's referral link and stats."""
    # Check channel membership first
    is_member = await check_channel_membership(message.from_user.id)
    if not is_member:
        await send_join_prompt(message)
        return
    
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    
    referral_count = 0
    try:
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(User.referral_count).where(User.user_id == message.from_user.id)
            )
            referral_count = count or 0
    except Exception:
        pass
    
    await message.answer(
        f"🔗 <b>Your Referral Dashboard</b>\n\n"
        f"📎 <b>Your Link:</b>\n<code>{referral_link}</code>\n\n"
        f"👥 <b>Total Referrals:</b> <code>{referral_count}</code>\n\n"
        f"Share your link — every new user who joins counts towards your referrals!",
        disable_web_page_preview=True
    )

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
    """Owner-only stats command with Superpowers Telemetry."""
    if str(message.from_user.id) not in settings.admin_list:
        return
    try:
        status_msg = await message.answer("⚡ <i>Gathering system telemetry & API health status...</i>")
        async with AsyncSessionLocal() as session:
            user_count = await session.scalar(select(func.count(User.id)))
            query_count = await session.scalar(select(func.count(QueryLog.id)))
            
            success_queries = await session.scalar(select(func.count(QueryLog.id)).where(QueryLog.status == 'success')) or 0
            banned_queries = await session.scalar(select(func.count(QueryLog.id)).where(QueryLog.status == 'not_found')) or 0
            
            # Referral stats
            total_referrals = await session.scalar(select(func.sum(User.referral_count))) or 0
            top_referrers_result = await session.execute(
                select(User.user_id, User.username, User.referral_count)
                .where(User.referral_count > 0)
                .order_by(User.referral_count.desc())
                .limit(5)
            )
            top_referrers = top_referrers_result.all()

        api_health = await tinder_client.ping_endpoints()
        health_text = "\n".join([f"• <code>{domain}</code>: {status}" for domain, status in api_health.items()])

        top_ref_text = ""
        if top_referrers:
            top_ref_text = "\n🏆 <b>Top Referrers:</b>\n"
            for i, (uid, uname, count) in enumerate(top_referrers, 1):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
                display = f"@{uname}" if uname else f"<code>{uid}</code>"
                top_ref_text += f"{medal} {display}: <code>{count}</code> referrals\n"

        stats_report = (
            f"⚡ <b>TINDER BOT SUPERPOWERS DASHBOARD</b> ⚡\n"
            f"═══════════════════════════════════════\n\n"
            f"📊 <b>Telemetry & Database:</b>\n"
            f"• Total Users: <code>{user_count}</code>\n"
            f"• Total Queries Run: <code>{query_count}</code>\n"
            f"• Active Profiles Found: <code>{success_queries}</code>\n"
            f"• Banned / Deleted Profiles: <code>{banned_queries}</code>\n\n"
            f"🔗 <b>Referral System:</b>\n"
            f"• Total Referrals: <code>{total_referrals}</code>\n"
            f"{top_ref_text}\n"
            f"🌐 <b>API Health Matrix (Multi-Failover):</b>\n"
            f"{health_text}\n\n"
            f"═══════════════════════════════════════"
        )
        await status_msg.edit_text(stats_report)
    except Exception as e:
        await message.answer(f"❌ DB Error: {html.escape(str(e))}")

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    """Owner-only users list command."""
    if str(message.from_user.id) not in settings.admin_list:
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).order_by(User.id.asc())
        )
        users = result.scalars().all()
        
    if not users:
        await message.answer("📝 No users registered yet.")
        return
        
    try:
        file_content = "👥 TINDER BOT REGISTERED USERS\n" + "="*30 + "\n\n"
        for i, user in enumerate(users, 1):
            name = user.full_name or "Unknown"
            username = user.username or "No Username"
            ref_count = user.referral_count or 0
            file_content += f"{i}. {name} (@{username}) | ID: {user.user_id} | Referrals: {ref_count}\n"
            
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
    
    success_count = 0
    failed = 0
    
    for uid in user_ids:
        try:
            if reply_msg:
                await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=reply_msg.message_id)
            else:
                await bot.send_message(chat_id=uid, text=broadcast_msg)
            success_count += 1
            await asyncio.sleep(0.05)
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

    # Force channel membership on every query
    is_member = await check_channel_membership(message.from_user.id)
    if not is_member:
        await send_join_prompt(message)
        return

    await register_user(message.from_user)
    user_id = message.from_user.id
    
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
    risk_info = data.get("risk_analysis", {})
    SEP = "═══════════════════════════════════════"
    
    if data["status"] == "not_found" or data.get("is_restricted"):
        status_text = "❌ BANNED / DELETED" if not data.get("is_restricted") else "🔴 SHADOWBANNED"
        report = (
            f"{SEP}\n"
            f"💣 Tinder DNA & OSINT Analysis 💥\n"
            f"{SEP}\n\n"
            f"🔴 Account: <code>{status_text}</code>\n"
            f"🛡️ Risk Rating: <b>{risk_info.get('badge', '🔴 HIGH RISK')}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪪 Username: <code>@{html.escape(username)}</code>\n\n"
            f"{SEP}\n"
            f"🧪 Analysis Complete\n"
            f"{SEP}"
        )
        await log_query(user_id, username, "not_found")
        await msg.delete()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌹 Open Profile", url=f"https://tinder.com/@{username}")],
            [InlineKeyboardButton(text="📢 Join Channel", url=CHANNEL_URL)]
        ])
        await message.answer(report, reply_markup=keyboard)
        
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
    
    creation_date_val = data.get("creation_date") or "Unknown"
    photos = data.get("photos_count") or 0
    age_value = data.get("age")
    name = html.escape(data.get("name") or "Hidden")
    birth_date = html.escape(data.get("birth_date") or "Hidden")
    account_age = data.get("account_age") or "Not available"
    account_id = data.get("account_id") or "Hidden"
    verified_str = "⚙️ Verified" if data.get("verified") else "⚙️ Not Verified"
    
    score_num = risk_info.get("score", 100)
    risk_level = risk_info.get("level", "🟢 Low Risk")
    
    if age_value and age_value != "Unknown":
        age_display = f"{age_value} years"
    else:
        age_display = "Unknown"
    
    if account_age == "Not available" and creation_date_val and creation_date_val != "Not available":
        account_age = str(creation_date_val)
    
    report = (
        f"{SEP}\n"
        f"🔥 Tinder DNA & OSINT Result ✨\n"
        f"{SEP}\n\n"
        f"🟢 Account Status: Active Account\n"
        f"🛡️ Risk Score: <b>{score_num}/100</b> ({risk_level})\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪪 Username: <code>@{html.escape(username)}</code>\n"
        f"👤 Display Name: {name}\n"
        f"🎂 Birth Date: {birth_date}\n"
        f"🕒 User Age: {age_display}\n"
        f"📸 Photos: {photos}\n"
        f"⏳ Account Age: {account_age}\n"
        f"📆 Registration: {html.escape(creation_date_val or 'Unknown')}\n"
        f"🆔 Account ID: <code>{account_id}</code>\n"
        f"⚙️ Verification: {verified_str}\n\n"
        f"{SEP}\n"
        f"🧪 Analysis Complete\n"
        f"{SEP}"
    )

    await msg.delete()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌹 Open Profile", url=f"https://tinder.com/@{username}")],
        [InlineKeyboardButton(text="💸 Sell This Account", url="https://t.me/T_ump"), InlineKeyboardButton(text="📢 Join Channel", url=CHANNEL_URL)]
    ])
    
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
                f"• <b>Risk Rating:</b> {risk_info.get('badge', '🟢 LOW RISK')}\n"
                f"• <b>Upstream Provider:</b> ⚙️ <code>{data.get('token_status') or 'Unknown'}</code>\n"
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
