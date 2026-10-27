from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.enums import ParseMode
from Script import script
from utils import check_verification, get_token
from info import (
    AUTH_PICS,
    BATCH_VERIFY,
    VERIFY,
    HOW_TO_VERIFY,
    AUTH_CHANNEL,
    ENABLE_LIMIT,
    RATE_LIMIT_TIMEOUT,
    MAX_FILES,
    BOT_USERNAME,
    FSUB
)
import time
import logging

logger = logging.getLogger(__name__)
rate_limit = {}

# ─────────────────────────────────────────────
# FORCE SUBSCRIBE CHECK (STRICT & FIXED)
# ─────────────────────────────────────────────
async def is_user_joined(bot, message: Message) -> bool:
    # FSUB OFF → allow everyone
    if not FSUB:
        return True

    user_id = message.from_user.id
    bot_user = await bot.get_me()
    not_joined_channels = []

    for channel_id in AUTH_CHANNEL:
        try:
            # Live membership check (every time)
            await bot.get_chat_member(channel_id, user_id)

        except UserNotParticipant:
            try:
                chat = await bot.get_chat(channel_id)

                # Safe invite link logic
                invite_link = (
                    chat.invite_link
                    or (f"https://t.me/{chat.username}" if chat.username else None)
                )

                if not invite_link:
                    invite_link = await bot.export_chat_invite_link(channel_id)

                not_joined_channels.append((chat.title, invite_link))

            except ChatAdminRequired:
                await message.reply_text(
                    (
                        "<i>🔒 Bot is not an admin in this channel.</i>\n\n"
                        "<b>Please contact the developer:</b>\n"
                        "<a href='https://t.me/SatyajeetKumarOfficial'>"
                        "<b>[ Click Here ]</b></a>"
                    ),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                return False

            except Exception as e:
                logger.error(f"[FSUB] Chat fetch error: {e}")
                return False  # ❌ no silent bypass

        except Exception as e:
            logger.error(f"[FSUB] get_chat_member error: {e}")
            return False  # ❌ no silent bypass

    # User has not joined required channels
    if not_joined_channels:
        buttons = [
            [InlineKeyboardButton(f"[{i+1}] {title}", url=link)]
            for i, (title, link) in enumerate(not_joined_channels)
        ]

        buttons.append([
            InlineKeyboardButton(
                "🔄 Try Again",
                url=f"https://t.me/{bot_user.username}?start=start"
            )
        ])

        await message.reply_photo(
            photo=AUTH_PICS,
            caption=script.AUTH_TXT.format(message.from_user.mention),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )
        return False

    return True


# ─────────────────────────────────────────────
# VERIFICATION (UNCHANGED – PASS THROUGH)
# ─────────────────────────────────────────────
async def rx_verification(client, message):
    return True

async def rx_x_verification(client, message):
    return True


# ─────────────────────────────────────────────
# RATE LIMIT (UNCHANGED)
# ─────────────────────────────────────────────
async def is_user_allowed(user_id):
    current_time = time.time()

    if ENABLE_LIMIT:
        if user_id in rate_limit:
            file_count, last_time = rate_limit[user_id]

            if file_count >= MAX_FILES and (current_time - last_time) < RATE_LIMIT_TIMEOUT:
                remaining_time = int(RATE_LIMIT_TIMEOUT - (current_time - last_time))
                return False, remaining_time

            elif file_count >= MAX_FILES:
                rate_limit[user_id] = [1, current_time]
            else:
                rate_limit[user_id][0] += 1
        else:
            rate_limit[user_id] = [1, current_time]

    return True, 0
