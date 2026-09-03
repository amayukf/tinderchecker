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

# ── In-memory cache to reduce Telegram API calls (Cloudflare-free friendly) ──
# Caches channel membership results for 10 minutes to save API quota
_membership_cache = {}  # {user_id: (is_member, timestamp)}
MEMBERSHIP_CACHE_TTL = 600  # 10 minutes

# Cache bot username so we don't call getMe on every request
_bot_username_cache = None

async def get_bot_username() -> str:
    global _bot_username_cache
    if not _bot_username_cache:
        info = await bot.get_me()
        _bot_username_cache = info.username
    return _bot_username_cache

async def init_db():
    """Initializes the database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for col_sql in [
            "ALTER TABLE users ADD COLUMN referred_by BIGINT",
            "ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN referral_verified BOOLEAN DEFAULT 0",
            "ALTER TABLE users ADD COLUMN query_count INTEGER DEFAULT 0",
        ]:
            try:
                await conn.execute(text(col_sql))
            except Exception:
                pass
    logger.info("Database initialized.")

async def check_channel_membership(user_id: int) -> bool:
    """Check if a user is a member of the required channel. Uses cache to reduce API calls."""
    now = time.time()
    cached = _membership_cache.get(user_id)
    if cached and (now - cached[1]) < MEMBERSHIP_CACHE_TTL:
        return cached[0]

    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        is_member = member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]
    except Exception as e:
        logger.error(f"Channel membership check failed: {e}")
        is_member = False

    _membership_cache[user_id] = (is_member, now)
    return is_member

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
    # Clear cache so we get a fresh check
    _membership_cache.pop(callback.from_user.id, None)
    is_member = await check_channel_membership(callback.from_user.id)
    if is_member:
        bot_username = await get_bot_username()
        ref_link = f"https://t.me/{bot_username}?start=ref_{callback.from_user.id}"
        await callback.message.edit_text(
            f"✅ <b>Verified!</b> You are now a member.\n\n"
            f"🔥 Send me any Tinder username to start checking!\n\n"
            f"📎 <b>Your referral link:</b>\n<code>{ref_link}</code>",
            disable_web_page_preview=True
        )
        await callback.answer("✅ Verified!", show_alert=False)
    else:
        await callback.answer("❌ You haven't joined yet! Please join the channel first.", show_alert=True)

async def register_user(tg_user: types.User, referred_by: int = None):
    """Saves or updates user info in the database."""
    if not tg_user:
        return
    try:
        async with AsyncSessionLocal() as session:
            existing = await session.scalar(select(User.id).where(User.user_id == tg_user.id))

            if existing:
                await session.execute(
                    update(User).where(User.user_id == tg_user.id).values(
                        username=tg_user.username,
                        full_name=tg_user.full_name
                    )
                )
            else:
                new_user = User(
                    user_id=tg_user.id,
                    username=tg_user.username,
                    full_name=tg_user.full_name,
                    referred_by=referred_by if referred_by and referred_by != tg_user.id else None,
                    referral_verified=False,
                    referral_count=0,
                    query_count=0
                )
                session.add(new_user)
            await session.commit()
    except Exception as e:
        logger.error(f"register_user failed: {e}")

async def try_verify_referral(user_id: int):
    """Anti-fraud: Verify a pending referral after the referred user makes a real query
    AND is still in the channel. Only runs once per user."""
    try:
        async with AsyncSessionLocal() as session:
            user = await session.scalar(
                select(User).where(User.user_id == user_id)
            )
            if not user or not user.referred_by or user.referral_verified:
                return  # No referral to verify, or already verified

            # Anti-fraud check 1: User must have at least 1 query (proves they're real)
            if (user.query_count or 0) < 1:
                return

            # Anti-fraud check 2: User must still be in the channel
            still_member = await check_channel_membership(user_id)
            if not still_member:
                return

            # ✅ Referral is verified! Credit the referrer
            await session.execute(
                update(User).where(User.user_id == user_id).values(referral_verified=True)
            )
            await session.execute(
                update(User).where(User.user_id == user.referred_by).values(
                    referral_count=User.referral_count + 1
                )
            )
            await session.commit()

            # Notify the referrer
            try:
                ref_name = user.full_name or "Someone"
                await bot.send_message(
                    chat_id=user.referred_by,
                    text=(
                        f"🎉 <b>Referral Confirmed!</b>\n\n"
                        f"<a href='tg://user?id={user_id}'>{html.escape(ref_name)}</a> "
                        f"used the bot and is verified as a real user.\n"
                        f"+1 referral credited to your account! 🏆"
                    )
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"try_verify_referral failed: {e}")

async def log_query(user_id: int, query: str, status: str):
    """Logs a query and increments user's query_count."""
    try:
        async with AsyncSessionLocal() as session:
            log = QueryLog(user_id=user_id, username_or_url=query, status=status)
            session.add(log)
            # Increment query_count for anti-fraud tracking
            await session.execute(
                update(User).where(User.user_id == user_id).values(
                    query_count=User.query_count + 1
                )
            )
            await session.commit()
    except Exception as e:
        logger.error(f"log_query failed: {e}")

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    referrer_id = None
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
        except ValueError:
            pass

    await register_user(message.from_user, referred_by=referrer_id)

    # Force channel join
    is_member = await check_channel_membership(message.from_user.id)
    if not is_member:
        await send_join_prompt(message)
        return

    bot_username = await get_bot_username()
    ref_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"

    welcome_text = (
        f"🔥 <b>Welcome to Tinder DNA Checker!</b> 🔥\n\n"
        f"🎯 Send any Tinder username to check.\n\n"
        f"<i>Examples:</i>  boy  •  @boy  •  tinder.com/@boy\n\n"
        f"📎 <b>Your referral link:</b>\n<code>{ref_link}</code>\n"
        f"Invite friends & earn verified referral credits!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Channel", url=CHANNEL_URL)]
    ])
    await message.answer(welcome_text, reply_markup=keyboard, disable_web_page_preview=True)

@dp.message(Command("refer"))
async def cmd_refer(message: types.Message):
    is_member = await check_channel_membership(message.from_user.id)
    if not is_member:
        await send_join_prompt(message)
        return

    bot_username = await get_bot_username()
    ref_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"

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
        f"🔗 <b>Referral Dashboard</b>\n\n"
        f"📎 <b>Your Link:</b>\n<code>{ref_link}</code>\n\n"
        f"👥 <b>Verified Referrals:</b> <code>{referral_count}</code>\n\n"
        f"ℹ️ Referrals are verified only after the invited user joins the channel AND uses the bot at least once.",
        disable_web_page_preview=True
    )

@dp.message(Command("debug"))
async def cmd_debug(message: types.Message):
    if str(message.from_user.id) not in settings.admin_list:
        return
    try:
        is_owner = str(message.from_user.id) == str(settings.OWNER_ID)
        status = "✅ Owner" if is_owner else "❌ User"
        await message.answer(
            f"🛠️ <b>Debug Info:</b>\n"
            f"• Your ID: <code>{message.from_user.id}</code>\n"
            f"• Owner ID: <code>{settings.OWNER_ID}</code>\n"
            f"• Match: {status}"
        )
    except Exception as e:
        logger.error(f"cmd_debug error: {e}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if str(message.from_user.id) not in settings.admin_list:
        return
    try:
        status_msg = await message.answer("⚡ <i>Loading dashboard...</i>")
        async with AsyncSessionLocal() as session:
            user_count = await session.scalar(select(func.count(User.id)))
            query_count = await session.scalar(select(func.count(QueryLog.id)))
            success_q = await session.scalar(select(func.count(QueryLog.id)).where(QueryLog.status == 'success')) or 0
            banned_q = await session.scalar(select(func.count(QueryLog.id)).where(QueryLog.status == 'not_found')) or 0
            total_referrals = await session.scalar(select(func.sum(User.referral_count))) or 0
            pending_referrals = await session.scalar(
                select(func.count(User.id)).where(User.referred_by.isnot(None), User.referral_verified == False)
            ) or 0
            top_result = await session.execute(
                select(User.user_id, User.username, User.referral_count)
                .where(User.referral_count > 0)
                .order_by(User.referral_count.desc())
                .limit(5)
            )
            top_referrers = top_result.all()

        api_health = await tinder_client.ping_endpoints()
        health_text = "\n".join([f"  • <code>{d}</code>: {s}" for d, s in api_health.items()])

        top_text = ""
        if top_referrers:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            top_text = "\n🏆 <b>Top Referrers:</b>\n"
            for i, (uid, uname, cnt) in enumerate(top_referrers):
                display = f"@{uname}" if uname else f"<code>{uid}</code>"
                top_text += f"  {medals[i]} {display}: <code>{cnt}</code>\n"

        report = (
            f"⚡ <b>SUPERPOWERS DASHBOARD</b> ⚡\n"
            f"═══════════════════════════════════════\n\n"
            f"📊 <b>Database:</b>\n"
            f"  • Users: <code>{user_count}</code>\n"
            f"  • Queries: <code>{query_count}</code>\n"
            f"  • Active found: <code>{success_q}</code>\n"
            f"  • Banned found: <code>{banned_q}</code>\n\n"
            f"🔗 <b>Referrals (Anti-Fraud):</b>\n"
            f"  • Verified: <code>{total_referrals}</code>\n"
            f"  • Pending: <code>{pending_referrals}</code>\n"
            f"{top_text}\n"
            f"🌐 <b>API Health:</b>\n"
            f"{health_text}\n\n"
            f"═══════════════════════════════════════"
        )
        await status_msg.edit_text(report)
    except Exception as e:
        await message.answer(f"❌ Error: {html.escape(str(e))}")

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if str(message.from_user.id) not in settings.admin_list:
        return
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.id.asc()))
        users = result.scalars().all()
    if not users:
        await message.answer("📝 No users yet.")
        return
    try:
        content = "👥 REGISTERED USERS\n" + "="*30 + "\n\n"
        for i, u in enumerate(users, 1):
            name = u.full_name or "Unknown"
            uname = u.username or "No Username"
            refs = u.referral_count or 0
            verified = "✅" if u.referral_verified else ("⏳" if u.referred_by else "—")
            content += f"{i}. {name} (@{uname}) | ID: {u.user_id} | Refs: {refs} | Status: {verified}\n"
        text_file = BufferedInputFile(content.encode("utf-8"), filename="users_list.txt")
        await message.answer_document(document=text_file, caption=f"✅ <b>Total:</b> <code>{len(users)}</code>")
    except Exception as e:
        await message.answer(f"❌ Error: {html.escape(str(e))}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if str(message.from_user.id) not in settings.admin_list:
        return
    broadcast_msg = message.text.replace("/broadcast", "", 1).strip()
    reply_msg = message.reply_to_message
    if not broadcast_msg and not reply_msg:
        await message.answer("⚠️ Provide a message or reply to one.")
        return
    status_msg = await message.answer("📢 <b>Broadcasting...</b>")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.user_id))
        user_ids = [row[0] for row in result.all()]
    ok, fail = 0, 0
    for uid in user_ids:
        try:
            if reply_msg:
                await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=reply_msg.message_id)
            else:
                await bot.send_message(chat_id=uid, text=broadcast_msg)
            ok += 1; await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await status_msg.edit_text(f"✅ <b>Done!</b> Sent: {ok} | Failed: {fail}")

@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return

    # Force channel membership
    is_member = await check_channel_membership(message.from_user.id)
    if not is_member:
        # Clear cache so next check is fresh
        _membership_cache.pop(message.from_user.id, None)
        await send_join_prompt(message)
        return

    await register_user(message.from_user)
    user_id = message.from_user.id

    current_time = time.time()
    if user_id in user_rate_limit and current_time - user_rate_limit[user_id] < RATE_LIMIT_SECONDS:
        remaining = int(RATE_LIMIT_SECONDS - (current_time - user_rate_limit[user_id]))
        await message.answer(f"⏳ Wait {remaining}s before next request.")
        return
    user_rate_limit[user_id] = current_time

    username = tinder_client.extract_username(message.text)
    if not username:
        await message.answer("❌ Invalid format. Send a Tinder URL or username.")
        return

    msg = await message.answer(f"🔍 Analyzing <b>{html.escape(username)}</b>...")

    data = await tinder_client.get_profile_data(username)
    risk_info = data.get("risk_analysis", {})
    SEP = "═══════════════════════════════════════"

    # Get referral link for footer
    bot_username = await get_bot_username()
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    if data["status"] == "not_found" or data.get("is_restricted"):
        status_text = "❌ BANNED / DELETED" if not data.get("is_restricted") else "🔴 SHADOWBANNED"
        report = (
            f"{SEP}\n💣 Tinder DNA & OSINT Analysis 💥\n{SEP}\n\n"
            f"🔴 Account: <code>{status_text}</code>\n"
            f"🛡️ Risk: <b>{risk_info.get('badge', '🔴 HIGH RISK')}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪪 Username: <code>@{html.escape(username)}</code>\n\n"
            f"{SEP}\n🧪 Analysis Complete\n{SEP}"
        )
        await log_query(user_id, username, "not_found")
        await msg.delete()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌹 Open Profile", url=f"https://tinder.com/@{username}")],
            [InlineKeyboardButton(text="📢 Channel", url=CHANNEL_URL)]
        ])
        await message.answer(report, reply_markup=keyboard)

        # Try to verify pending referral in background
        asyncio.create_task(try_verify_referral(user_id))

        if settings.admin_list and str(user_id) not in settings.admin_list:
            try:
                user = message.from_user
                await bot.send_message(
                    chat_id=settings.admin_list[0],
                    text=(
                        f"📊 <b>Query (Inactive)</b>\n"
                        f"• <a href='tg://user?id={user.id}'>{html.escape(user.full_name or 'Unknown')}</a>\n"
                        f"• Profile: @{html.escape(username)}\n"
                        f"• Status: ❌ Banned/Deleted"
                    )
                )
            except Exception: pass
        return

    elif data["status"] == "error":
        await log_query(user_id, username, "error")
        await msg.edit_text("⚠️ Error fetching profile. Try again later.")
        return

    await log_query(user_id, username, "success")

    # Try to verify pending referral in background
    asyncio.create_task(try_verify_referral(user_id))

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
    age_display = f"{age_value} years" if age_value and age_value != "Unknown" else "Unknown"

    if account_age == "Not available" and creation_date_val not in ("Not available", "Unknown"):
        account_age = str(creation_date_val)

    report = (
        f"{SEP}\n🔥 Tinder DNA & OSINT Result ✨\n{SEP}\n\n"
        f"🟢 Account: Active\n"
        f"🛡️ Risk: <b>{score_num}/100</b> ({risk_level})\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪪 Username: <code>@{html.escape(username)}</code>\n"
        f"👤 Name: {name}\n"
        f"🎂 Birth: {birth_date}\n"
        f"🕒 Age: {age_display}\n"
        f"📸 Photos: {photos}\n"
        f"⏳ Account Age: {account_age}\n"
        f"📆 Registered: {html.escape(creation_date_val)}\n"
        f"🆔 ID: <code>{account_id}</code>\n"
        f"⚙️ Verified: {verified_str}\n\n"
        f"{SEP}\n🧪 Analysis Complete\n{SEP}\n\n"
        f"📎 Invite friends: <code>{ref_link}</code>"
    )

    await msg.delete()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌹 Open Profile", url=f"https://tinder.com/@{username}")],
        [InlineKeyboardButton(text="💸 Sell Account", url="https://t.me/T_ump"), InlineKeyboardButton(text="📢 Channel", url=CHANNEL_URL)]
    ])

    if settings.admin_list and str(user_id) not in settings.admin_list:
        try:
            user = message.from_user
            status_log = "⚠️ Limited" if data.get("is_restricted") else "✅ Active"
            await bot.send_message(
                chat_id=settings.admin_list[0],
                text=(
                    f"📊 <b>Query (Success)</b>\n"
                    f"• <a href='tg://user?id={user.id}'>{html.escape(user.full_name or 'Unknown')}</a>\n"
                    f"• Profile: @{html.escape(username)}\n"
                    f"• Risk: {risk_info.get('badge', '🟢')}\n"
                    f"• Via: <code>{data.get('token_status', 'Unknown')}</code>\n"
                    f"• Status: {status_log}"
                )
            )
        except Exception: pass

    if data.get("image_url"):
        try:
            await message.answer_photo(photo=data["image_url"], caption=report, reply_markup=keyboard)
        except Exception:
            await message.answer(report, disable_web_page_preview=True, reply_markup=keyboard)
    else:
        await message.answer(report, disable_web_page_preview=True, reply_markup=keyboard)
