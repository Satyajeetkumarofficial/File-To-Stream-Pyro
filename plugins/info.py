from pyrogram import Client, filters
from pyrogram.types import Message
from datetime import datetime
from database.users_db import db  # Your DB class instance

@Client.on_message(filters.private & filters.command("info"))
async def user_info_command(client: Client, message: Message):
    user = message.from_user
    user_id = user.id
    name = user.first_name or "Unknown"
    username = user.username or "None"
    lang_code = user.language_code or "en"

    # Total Files Uploaded
    file_count = await db.files.count_documents({"user_id": user_id})

    # Premium Status
    is_premium = await db.has_premium_access(user_id)

    # Verification Info
    verified = await db.get_verified(user_id)
    verification_date = verified.get("date", "❌ Not Verified")
    verification_time = verified.get("time", "")

    # Block Status
    is_blocked = await db.is_user_blocked(user_id)
    block_text = "🚫 Blocked" if is_blocked else "✅ Not Blocked"

    # Telegram Status (UserStatus.RECENTLY, etc.)
    try:
        user_status = (await client.get_chat(user_id)).status
    except:
        user_status = "Unknown"

    # Final Message
    text = f"""
<b>User Details :</b>

🧾 <b>Name :</b> <code>{name}</code>
👤 <b>User Id :</b> <code>{user_id}</code>
📁 <b>Total Files Uploaded :</b> <code>{file_count}</code>
👱 <b>UserName :</b> <code>{username}</code>
⭐ <b>Premium User :</b> <code>{is_premium}</code>
💬 <b>Language Code :</b> <code>{lang_code}</code>
🌸 <b>Status :</b> <code>{user_status}</code>
🛑 <b>Block Status :</b> <code>{block_text}</code>
🗓️ <b>Verified On :</b> <code>{verification_date} {verification_time}</code>
"""

    await message.reply_text(text, quote=True)
