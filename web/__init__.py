from aiohttp import web
from .stream_routes import routes
from asyncio import sleep
from datetime import datetime, timedelta
from database.users_db import db
from info import PREMIUM_LOGS
from pyrogram import Client

import logging
import time as _time
from os import environ

_req_log = logging.getLogger("request")
# LOG_REQUESTS: "errors" (default: only status >= 400), "all", or "off"
_LOG_MODE = environ.get("LOG_REQUESTS", "errors").strip().lower()


@web.middleware
async def log_middleware(request, handler):
    t0 = _time.monotonic()
    status, err = 0, None
    try:
        resp = await handler(request)
        status = getattr(resp, "status", 0)
        return resp
    except web.HTTPException as e:
        status, err = e.status, e.text
        raise
    except BaseException as e:
        status, err = 500, repr(e)
        raise
    finally:
        if _LOG_MODE != "off" and request.path not in ("/health",) and (_LOG_MODE == "all" or status >= 400):
            _req_log.info(
                "%s %s -> %s %.2fs ip=%s range=%s ua=%s%s",
                request.method, request.path, status, _time.monotonic() - t0,
                request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For") or request.remote,
                request.headers.get("Range", "-"), (request.headers.get("User-Agent") or "-")[:40],
                f" err={err}" if err else "",
            )


async def web_server():
    web_app = web.Application(client_max_size=30000000, middlewares=[log_middleware])
    web_app.add_routes(routes)
    return web_app

REMINDER_TIMES = [
    ("1d", timedelta(days=1)),
    ("5h30m", timedelta(hours=5, minutes=30)),
    ("50m", timedelta(minutes=50))
]

async def check_expired_premium(client):
    while True:
        now = datetime.utcnow()
        expired_users = await db.get_expired(now)
        for user in expired_users:
            user_id = user["id"]
            await db.remove_premium_access(user_id)
            unset_flags = {f"reminder_{label}_sent": "" for label, _ in REMINDER_TIMES}
            await db.users.update_one({"id": user_id}, {"$unset": unset_flags})
            try:
                tg_user = await client.get_users(user_id)
                await client.send_message(
                    user_id,
                    f"<b>ʜᴇʏ {tg_user.mention},\n\nʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss ʜᴀs ᴇxᴘɪʀᴇᴅ.\n\nTᴀᴘ /plan ꜰᴏʀ ʀᴇɴᴇᴡᴀʟ ᴏᴘᴛɪᴏɴs.</b>"
                )
                await client.send_message(
                    PREMIUM_LOGS,
                    f"<b>#Premium_Expired\nUser: {tg_user.mention}\nID: <code>{user_id}</code></b>"
                )
            except Exception as e:
                print(f"[EXPIRED ERROR] {e}")
            await sleep(0.5)
        for label, delta in REMINDER_TIMES:
            reminder_users = await db.get_expiring_soon(label, delta)
            for user in reminder_users:
                user_id = user["id"]
                try:
                    tg_user = await client.get_users(user_id)
                    await client.send_message(
                        user_id,
                        f"<b>ʜᴇʏ {tg_user.mention},\n\nʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴡɪʟʟ ᴇxᴘɪʀᴇ ɪɴ {label}.\nTᴀᴘ /plan ᴛᴏ ʀᴇɴᴇᴡ ɴᴏᴡ!</b>"
                    )
                    await client.send_message(
                        PREMIUM_LOGS,
                        f"<b>#Reminder ({label})\nUser: {tg_user.mention}\nID: <code>{user_id}</code></b>"
                    )
                except Exception as e:
                    print(f"[REMINDER ERROR] {e}")
                await sleep(0.5)
        await sleep(60)
