import logging
from pyrogram import Client, types
from typing import Union, Optional, AsyncGenerator
from info import *
from utils import Temp

# Logging Setup (Better)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
for mod in ["aiohttp", "pyrogram", "aiohttp.web"]:
    logging.getLogger(mod).setLevel(logging.ERROR)




def _stored_session():
    """Login saved in MongoDB by session_store (sync read, once, at import time)."""
    try:
        from pymongo import MongoClient
        c = MongoClient(DB_URL, serverSelectionTimeoutMS=8000)
        try:
            doc = c[DB_NAME].bot_sessions.find_one({"_id": BOT_TOKEN.split(":")[0]})
            return (doc or {}).get("session")
        finally:
            c.close()
    except Exception as e:
        logging.warning("stored login not available: %r", e)
        return None


class WebXBot(Client):
    def __init__(self):
        stored = _stored_session()
        super().__init__(
            name=SESSION,
            session_string=stored,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=WORKERS,
            plugins={"root": "plugins"},
            sleep_threshold=SLEEP_THRESHOLD,
        )
        self.stored_login = stored

    async def set_self(self):
        Temp.BOT = self

    async def iter_messages(
        self,
        chat_id: Union[int, str],
        limit: int,
        offset: int = 0,
    ) -> AsyncGenerator["types.Message", None]:
        """
        Asynchronously iterate through messages in a chat.
        Uses batching with a max of 200 messages per request.
        """
        current = offset
        while current < limit:
            batch_size = min(200, limit - current)
            ids = list(range(current, current + batch_size))
            messages = await self.get_messages(chat_id, ids)

            if not messages:
                break

            for msg in messages:
                if msg:  # Skip None
                    yield msg

            current += batch_size  # Increment by batch length


# ✅ Global single client instance
StreamBot = WebXBot()

# ✅ Client management setup
multi_clients = {}
work_loads = {}
