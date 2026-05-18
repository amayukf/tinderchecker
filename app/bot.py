import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from app.config import settings
from app.tinder_client import TinderClient

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
tinder_client = TinderClient()

# Extremely simple in-memory rate limiting (Note: In Vercel, this is ephemeral per instance)
user_rate_limit = {}
RATE_LIMIT_SECONDS = 5

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join", url="https://t.me/N_Notic")]
    ])
    
    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.message()
async def analyze_profile(message: types.Message):
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

    msg = await message.answer(f"🔍 Analyzing profile for <b>{username}</b>...")
    
    data = await tinder_client.get_profile_data(username)
    
    if data["status"] == "not_found":
        await msg.edit_text(f"❌ Profile not active")
        # Log failure to owner
        if settings.OWNER_ID:
            try:
                user = message.from_user
                is_premium = "👑 Yes" if user.is_premium else "❌ No"
                log_text = (
                    f"📊 <b>Bot Query (Inactive Profile)</b>\n\n"
                    f"• <b>User:</b> <a href='tg://user?id={user.id}'>{user.full_name}</a>\n"
                    f"• <b>Username:</b> {f'@{user.username}' if user.username else 'No Username'}\n"
                    f"• <b>User ID:</b> <code>{user.id}</code>\n"
                    f"• <b>Language:</b> 🌐 <code>{user.language_code or 'Unknown'}</code>\n"
                    f"• <b>Telegram Premium:</b> {is_premium}\n"
                    f"• <b>Queried Profile:</b> @{username}\n"
                    f"• <b>Status:</b> ❌ Profile not active"
                )
                await bot.send_message(chat_id=settings.OWNER_ID, text=log_text)
            except Exception:
                pass
        return
    elif data["status"] == "error":
        await msg.edit_text("⚠️ An error occurred while fetching the profile. Please try again later.")
        return
        
    bot_info = await bot.get_me()
    
    if data.get("is_restricted"):
        report = (
            f"⚠️ <b>Account Limited</b>\n\n"
            f"👤 <b>Username:</b> @{username}\n"
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
            f"• Username: @{username}\n"
            f"• Display Name: {data.get('name') or 'N/A'}\n"
            f"• User Age: {data.get('age') or 'Unknown'} years\n"
            f"• Birth Date: {data.get('birth_date') or 'Hidden'}\n"
            f"• Job/Work: {data.get('jobs') or 'Not Specified'}\n"
            f"• School/Uni: {data.get('schools') or 'Not Specified'}\n"
            f"• Total Photos: 📸 {data.get('photos_count') or 'Unknown'} upload(s)\n"
            f"• Bio: <i>\"{data.get('bio') or 'No bio written.'}\"</i>\n\n"
            f"• Account Age: {data.get('account_age') or 'Unknown'}\n"
            f"• Registration Time: {data.get('creation_date') or 'Unknown'}\n"
            f"• Account ID: <code>{data.get('account_id') or 'Unknown'}</code>\n\n"
            f"Official Link: https://tinder.com/@{username}\n\n"
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
    
    # Log success to owner
    if settings.OWNER_ID:
        try:
            user = message.from_user
            is_premium = "👑 Yes" if user.is_premium else "❌ No"
            status_log = "⚠️ Limited Account" if data.get("is_restricted") else "✅ Active Account"
            log_text = (
                f"📊 <b>New Bot Query (Success)!</b>\n\n"
                f"• <b>User:</b> <a href='tg://user?id={user.id}'>{user.full_name}</a>\n"
                f"• <b>Username:</b> {f'@{user.username}' if user.username else 'No Username'}\n"
                f"• <b>User ID:</b> <code>{user.id}</code>\n"
                f"• <b>Language:</b> 🌐 <code>{user.language_code or 'Unknown'}</code>\n"
                f"• <b>Telegram Premium:</b> {is_premium}\n"
                f"• <b>Queried Profile:</b> @{username}\n"
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
