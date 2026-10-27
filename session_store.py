"""
Keeps every bot's login (session string) in MongoDB.

Why: Koyeb/Render/Heroku containers lose local files on every restart or redeploy, and
Telegram allows only a few fresh bot logins (auth.ImportBotAuthorization) - after a crash
loop it answers "FLOOD_WAIT 1748s" and the bot stays dead for half an hour. With a stored
session a restart re-uses the old login and no new login is needed.
"""
import logging

from database.users_db import mydb

log = logging.getLogger("session")
_col = mydb.bot_sessions


def _key(token: str) -> str:
    return token.split(":")[0]


async def load(token: str):
    try:
        doc = await _col.find_one({"_id": _key(token)})
        return (doc or {}).get("session")
    except Exception as e:
        log.warning("could not read stored session: %r", e)
        return None


async def save(token: str, client) -> None:
    try:
        session = await client.export_session_string()
        await _col.update_one({"_id": _key(token)}, {"$set": {"session": session}}, upsert=True)
    except Exception as e:
        log.warning("could not store session: %r", e)


async def forget(token: str) -> None:
    try:
        await _col.delete_one({"_id": _key(token)})
    except Exception as e:
        log.warning("could not delete stored session: %r", e)


def is_flood(exc: BaseException) -> int:
    """Seconds to wait if `exc` is a FloodWait, else 0."""
    if type(exc).__name__ == "FloodWait":
        return int(getattr(exc, "value", None) or getattr(exc, "x", None) or 60)
    return 0


BAD_SESSION = {"AuthKeyUnregistered", "AuthKeyInvalid", "AuthKeyDuplicated", "SessionRevoked",
               "SessionExpired", "Unauthorized", "UserDeactivated", "AccessTokenInvalid"}
