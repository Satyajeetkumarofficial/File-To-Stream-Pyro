from pyrogram import Client
from typing import Any, Optional
from pyrogram.types import Message
from pyrogram.file_id import FileId
from pyrogram.raw.types.messages import Messages
import asyncio
import logging

from web.server.exceptions import InvalidHash, FIleNotFound as FileNotFound  # noqa: E402

# ✅ Media Extractor Function
def get_media_from_message(message: "Message") -> Optional[Any]:
    media_types = (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    )
    for attr in media_types:
        media = getattr(message, attr, None)
        if media:
            return media
    return None

# ✅ File ID Parser
async def parse_file_id(message: "Message") -> Optional[FileId]:
    media = get_media_from_message(message)
    if media and getattr(media, "file_id", None):
        return FileId.decode(media.file_id)
    return None

# ✅ File Unique ID Parser
async def parse_file_unique_id(message: "Message") -> Optional[str]:
    media = get_media_from_message(message)
    if media:
        return getattr(media, "file_unique_id", None)
    return None

# ✅ Main Function to Extract File Info
async def get_file_ids(client: Client, chat_id: int, id: int) -> Optional[FileId]:
    message = None
    last_err = None
    for attempt in range(3):
        try:
            message = await client.get_messages(chat_id, id)
            break
        except Exception as e:  # FloodWait / network hiccup -> retry a few times
            last_err = e
            if type(e).__name__ == "FloodWait":
                wait = int(getattr(e, "value", None) or getattr(e, "x", None) or 1)
                if wait > 20:
                    break
                await asyncio.sleep(wait + 0.5)
            else:
                await asyncio.sleep(0.5 * (attempt + 1))
    else:
        message = None

    if message is None:
        logging.error(f"Error getting message {id}: {last_err}")
        raise FileNotFound("Message could not be fetched from Telegram")

    if isinstance(message, list):
        message = message[0] if message else None
    if not message or message.empty:
        raise FileNotFound("Message is empty or invalid")

    media = get_media_from_message(message)
    if not media:
        raise FileNotFound("No media found in message")

    file_id = await parse_file_id(message)
    file_unique_id = await parse_file_unique_id(message)

    if not file_id:
        raise FileNotFound("File ID could not be parsed")

    # ✅ Set file properties safely
    setattr(file_id, "file_size", getattr(media, "file_size", 0) or 0)
    setattr(file_id, "mime_type", getattr(media, "mime_type", None) or "application/octet-stream")
    setattr(file_id, "file_name", getattr(media, "file_name", None) or "Unnamed")
    setattr(file_id, "unique_id", file_unique_id or "XXXXXX")
    setattr(file_id, "file_id_str", getattr(media, "file_id", None))

    return file_id

# ✅ Generate 6-digit Hash
def get_hash(media_msg: Message) -> str:
    media = get_media_from_message(media_msg)
    if media:
        return getattr(media, "file_unique_id", "")[:6]
    return "000000"

