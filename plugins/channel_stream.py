import asyncio
from web.utils.file_properties import get_hash
from pyrogram import Client, filters
from info import (
    BIN_CHANNEL, URL, BOT_USERNAME,
    IS_SHORTLINK, HOW_TO_OPEN, NO_STREAM_CHANNELS
)
from utils import get_shortlink
from database.users_db import db
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton


@Client.on_message(
    filters.channel & (filters.document | filters.video) & ~filters.forwarded,
    group=-1
)
async def channel_receive_handler(bot: Client, broadcast: Message):
    try:
        chat_id = broadcast.chat.id

        # ───── Channel ban check ─────
        if str(chat_id).startswith("-100"):
            if await db.is_channel_blocked(chat_id):
                try:
                    await bot.send_message(
                        chat_id,
                        "🚫 **This channel is banned from using the bot.**\n\n"
                        "🔄 **Cᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ ɪғ ʏᴏᴜ ᴛʜɪɴᴋ ᴛʜɪꜱ ɪꜱ ᴀ ᴍɪꜱᴛᴀᴋᴇ.**\n\n@ProBotUpdate"
                    )
                except:
                    pass
                await bot.leave_chat(chat_id)
                return

        # ───── Forward file to BIN_CHANNEL ─────
        msg = await broadcast.forward(chat_id=BIN_CHANNEL)

        # ───── Streaming control ─────
        stream_disabled = chat_id in NO_STREAM_CHANNELS

        raw_stream = (
            None if stream_disabled
            else f"{URL}watch/{msg.id}/ProBotz.mkv?hash={get_hash(msg)}"
        )
        raw_download = f"{URL}{msg.id}?hash={get_hash(msg)}"
        raw_file_link = f"https://t.me/{BOT_USERNAME}?start=file_{msg.id}"

        if IS_SHORTLINK:
            stream = None if stream_disabled else await get_shortlink(raw_stream)
            download = await get_shortlink(raw_download)
            file_link = await get_shortlink(raw_file_link)
        else:
            stream = raw_stream
            download = raw_download
            file_link = raw_file_link

        # ───── Build buttons (ONLY if streaming enabled) ─────
        buttons_list = []

        if not stream_disabled:
            buttons_list.append([
                InlineKeyboardButton(" ꜱᴛʀᴇᴀᴍ ", url=stream),
                InlineKeyboardButton(" ᴅᴏᴡɴʟᴏᴀᴅ ", url=download)
            ])
            buttons_list.append([
                InlineKeyboardButton(" ᴄʜᴇᴄᴋ ʜᴇʀᴇ ᴛᴏ ɢᴇᴛ ғɪʟᴇ ", url=file_link)
            ])
            if IS_SHORTLINK:
                buttons_list.append([
                    InlineKeyboardButton("• ʜᴏᴡ ᴛᴏ ᴏᴘᴇɴ •", url=HOW_TO_OPEN)
                ])

        buttons = InlineKeyboardMarkup(buttons_list) if buttons_list else None

        # ───── IMPORTANT: Caption NOT touched ─────
        if buttons is not None:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=broadcast.chat.id,
                    message_id=broadcast.id,
                    reply_markup=buttons
                )
            except:
                pass

    except asyncio.exceptions.TimeoutError:
        await asyncio.sleep(5)
        await channel_receive_handler(bot, broadcast)

    except FloodWait as w:
        await asyncio.sleep(w.value)

    except Exception as e:
        try:
            if str(e).strip():
                await bot.send_message(
                    chat_id=BIN_CHANNEL,
                    text=f"❌ **Error:** `{e}`",
                    disable_web_page_preview=True
                )
        except:
            pass
        print(f"❌ Can't edit channel message! Error: {e}")
