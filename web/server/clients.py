import asyncio
import logging

import session_store
from info import API_ID, API_HASH, BOT_TOKEN, SLEEP_THRESHOLD, MAX_CLIENTS, MEMORY_LIMIT_MB
from pyrogram import Client
from web.utils.config_parser import TokenParser
from web.server import multi_clients, work_loads, StreamBot

log = logging.getLogger("clients")


async def _start_one(client_id: int, token: str) -> bool:
    """Start one extra bot (re-using its stored login). Returns True when it is serving."""
    stored = await session_store.load(token)
    for attempt in range(3):
        try:
            client = Client(
                name=f"RXClient_{client_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=token,
                session_string=stored,
                sleep_threshold=SLEEP_THRESHOLD,
                no_updates=True,
                in_memory=True,
            )
            await client.start()
            if not stored:
                await session_store.save(token, client)
            multi_clients[client_id] = client
            work_loads[client_id] = 0
            log.info("Extra client %s is up (%s)", client_id, "stored login" if stored else "fresh login")
            return True
        except Exception as e:
            wait = session_store.is_flood(e)
            if wait:
                log.error("Client %s: Telegram login FloodWait %ss - will retry in the background", client_id, wait)
                asyncio.create_task(_retry_later(client_id, token, wait))
                return False
            if stored and session_store.unusable(e):
                log.warning("Client %s: stored login rejected, logging in again", client_id)
                await session_store.forget(token)
                stored = None
                continue
            log.error("Failed to start client %s: %r", client_id, e)
            await asyncio.sleep(3 * (attempt + 1))
    return False


async def _retry_later(client_id: int, token: str, wait: int):
    await asyncio.sleep(wait + 5)
    if not await _start_one(client_id, token):
        log.error("Client %s could not be started in the background", client_id)


async def initialize_clients():
    multi_clients[0] = StreamBot
    work_loads[0] = 0

    all_tokens = TokenParser().parse_from_env()

    # never start the main token (or a duplicate) twice - Telegram would fight over the session
    seen = {BOT_TOKEN.strip()}
    unique = {}
    for cid, token in all_tokens.items():
        t = token.strip()
        if t in seen:
            log.warning("MULTI_TOKEN%s duplicates another token - skipped", cid)
            continue
        seen.add(t)
        unique[cid] = t

    if MAX_CLIENTS and len(unique) > MAX_CLIENTS - 1:
        keep = list(unique.items())[: max(0, MAX_CLIENTS - 1)]
        log.warning(
            "RAM limit %s MB: using only %s of %s bot clients (set MAX_CLIENTS to change). Extra tokens ignored: %s",
            int(MEMORY_LIMIT_MB) if MEMORY_LIMIT_MB else "?", MAX_CLIENTS, len(unique) + 1,
            [k for k in unique if k not in dict(keep)],
        )
        unique = dict(keep)

    if not unique:
        log.warning("No additional clients found, using the default client only")
        return

    gate = asyncio.Semaphore(2)  # 2 at a time: gentle on Telegram AND on RAM during startup

    async def guarded(cid, tok):
        async with gate:
            return await _start_one(cid, tok)

    await asyncio.gather(*[guarded(i, t) for i, t in unique.items()])

    if len(multi_clients) > 1:
        log.info("✅ Multi-client mode: %s bots active", len(multi_clients))
    else:
        log.warning("No additional clients were initialized, using the default client only.")
