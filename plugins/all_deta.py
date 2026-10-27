import sys
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from info import ADMINS
from database.users_db import db

# ✅ Bot Stats Command
@Client.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def bot_stats(client: Client, message: Message):
    total_users = await db.total_users_count()
    premium_users = await db.all_premium_users_count()
    blocked_users = await db.total_blocked_count()
    blocked_channels = await db.total_blocked_channels_count()
    total_files = await db.files.count_documents({})
    verified_users = await db.get_verified_users_count()  # ✅ Use your function here

    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 <b>Total Users:</b> <code>{total_users}</code>\n"
        f"⭐ <b>Premium Users:</b> <code>{premium_users}</code>\n"
        f"✅ <b>Verified Users:</b> <code>{verified_users}</code>\n"
        f"🚫 <b>Blocked Users:</b> <code>{blocked_users}</code>\n"
        f"📛 <b>Blocked Channels:</b> <code>{blocked_channels}</code>\n"
        f"🗂️ <b>Total Files Uploaded:</b> <code>{total_files}</code>"
    )

    await message.reply_text(
        text=text,
        quote=True,
        disable_web_page_preview=True
    )

# 🔁 Restart Command
@Client.on_message(filters.private & filters.command("restart") & filters.user(ADMINS))
async def restart(client: Client, message: Message):
    msg = await message.reply_text("<i>♻️ Restarting the bot, please wait...</i>")
    await asyncio.sleep(2)
    try:
        await msg.edit("<i>✅ Bot restarted successfully!</i>")
    except:
        pass
    os.execl(sys.executable, sys.executable, *sys.argv)
