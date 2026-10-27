# NOTE: compat_pyrogram must be imported first - it makes `import pyrogram` work
# whether the installed package exposes `pyrogram` (Pyrofork) or `hydrogram`.
import compat_pyrogram  # noqa: F401  (isort: skip)

import asyncio
import logging
from datetime import date, datetime

import pytz

# ================= EVENT LOOP (uvloop when available) =================
try:
    import uvloop
    loop = uvloop.new_event_loop()
except Exception:  # not installed / not supported -> plain asyncio
    loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
# ======================================================================

from pyrogram import idle
import pyrogram.utils as _pyro_utils

# ---- newer channel ids: keep the library's own logic, only add a safe fallback ----
_orig_get_peer_type = getattr(_pyro_utils, "get_peer_type", None)


def _get_peer_type_safe(peer_id: int) -> str:
    if _orig_get_peer_type is not None:
        try:
            return _orig_get_peer_type(peer_id)
        except ValueError:
            pass
    s = str(peer_id)
    if not s.startswith("-"):
        return "user"
    if s.startswith("-100"):
        return "channel"
    return "chat"


_pyro_utils.get_peer_type = _get_peer_type_safe
try:
    if getattr(_pyro_utils, "MIN_CHANNEL_ID", 0) > -1002822095763:
        _pyro_utils.MIN_CHANNEL_ID = -1002822095763
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
for _name in ("aiohttp", "aiohttp.web", "aiohttp.access", "pyrogram", "hydrogram", "wzgram"):
    logging.getLogger(_name).setLevel(logging.ERROR)

from aiohttp import web                                   # noqa: E402
from info import *                                        # noqa: E402,F401,F403
from Script import script                                 # noqa: E402
from web import web_server, check_expired_premium         # noqa: E402
from web.server import StreamBot, multi_clients           # noqa: E402
from web.server.clients import initialize_clients         # noqa: E402
from utils import Temp, ping_server                       # noqa: E402
import session_store                                      # noqa: E402
import memguard                                           # noqa: E402

log = logging.getLogger("bot")


async def _supervise(name, fn, *args):
    """Run a background job forever; if it crashes, log and restart it."""
    while True:
        try:
            await fn(*args)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Background task %s crashed - restarting in 30s", name)
            await asyncio.sleep(30)


async def _notify(chat_id, text):
    if not chat_id:
        return
    try:
        await StreamBot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        log.warning("Could not notify %s: %r", chat_id, e)


async def _login_main():
    """Start the main bot re-using its stored login; survive login FloodWaits."""
    stored = getattr(StreamBot, "stored_login", None)
    if stored:
        log.info("Using stored login for the main bot")

    for attempt in range(8):
        try:
            await StreamBot.start()          # also loads everything in /plugins
            if not stored:
                await session_store.save(BOT_TOKEN, StreamBot)
            return
        except Exception as e:
            wait = session_store.is_flood(e)
            if wait:
                log.error("Telegram login FloodWait %ss - waiting it out (web server stays up)", wait)
                await asyncio.sleep(wait + 5)
                continue
            if type(e).__name__ in session_store.BAD_SESSION and stored:
                log.warning("Stored login rejected - forgetting it, using a fresh login")
                await session_store.forget(BOT_TOKEN)
                stored = None
                raise SystemExit("Stored login was invalid; restart once to log in fresh")
            raise
    raise SystemExit("Could not log in to Telegram")


async def start():
    print("\nInitializing Your Bot")
    try:
        import pyrogram as _lib
        log.info("Telegram library: %s %s", compat_pyrogram.BACKEND, getattr(_lib, "__version__", "?"))
    except Exception:
        pass

    # web server FIRST: platform health checks pass while the bot logs in
    runner = web.AppRunner(await web_server(), access_log=None, keepalive_timeout=75)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT, backlog=2048).start()
    log.info("Web server listening on port %s", PORT)

    await _login_main()
    await initialize_clients()

    me = await StreamBot.get_me()
    Temp.BOT = StreamBot
    Temp.ME = me.id
    Temp.U_NAME = me.username
    Temp.B_NAME = me.first_name
    log.info("Bot @%s ready with %s bot client(s)", me.username, len(multi_clients))

    tasks = [asyncio.create_task(_supervise("premium-check", check_expired_premium, StreamBot)),
             asyncio.create_task(_supervise("memory-trim", memguard.trimmer))]
    if ON_HEROKU:
        tasks.append(asyncio.create_task(_supervise("ping", ping_server)))

    tz = pytz.timezone("Asia/Kolkata")
    today = date.today()
    now = datetime.now(tz).strftime("%H:%M:%S %p")
    await _notify(LOG_CHANNEL, script.RESTART_TXT.format(today, now))
    await _notify(ADMINS[0] if ADMINS else 0, "<b>ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ !!</b>")
    await _notify(SUPPORT_GROUP, f"<b>{me.mention} ʀᴇsᴛᴀʀᴛᴇᴅ 🤖</b>")

    try:
        await idle()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runner.cleanup()
        for c in list(multi_clients.values()):
            if c is not StreamBot:
                try:
                    await c.stop()
                except Exception:
                    pass
        try:
            await StreamBot.stop()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        loop.run_until_complete(start())
    except KeyboardInterrupt:
        log.info("----------------------- Service Stopped -----------------------")
