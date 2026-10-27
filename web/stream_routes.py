import re
import time
import logging
import secrets
import asyncio
import urllib.parse
from contextlib import aclosing, suppress

from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine

from info import (
    BOT_USERNAME,
    MAX_CONCURRENT_STREAMS,
    MAX_STREAMS_PER_IP,
    MEM_SHED_RATIO,
    STALL_TIMEOUT,
    STREAM_QUEUE_TIMEOUT,
    SETTINGS_CACHE_TTL,
)
from web.server import multi_clients, work_loads
from web.server.exceptions import FIleNotFound, InvalidHash
import memguard
from database.users_db import db
from web.utils.custom_dl import (
    Busy, get_byte_streamer, stream_file, compute_geometry, active_streams, active_lanes,
    pick_client_index, STATS,
)
from utils import get_readable_time
from web.utils import StartTime, __version__
from web.utils.render_template import render_page
from web.utils import diskcache

log = logging.getLogger("web")
routes = web.RouteTableDef()

CHUNK_SIZE = 1024 * 1024
PATH_RE = re.compile(r"^([a-zA-Z0-9_-]{6})(\d+)$")
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")

# ---------------------------------------------------------------- limiters
_stream_slots = None            # asyncio.Semaphore, created lazily inside the loop
_waiting = 0
_per_ip: dict = {}


def _slots() -> asyncio.Semaphore:
    global _stream_slots
    if _stream_slots is None:
        _stream_slots = asyncio.Semaphore(MAX_CONCURRENT_STREAMS)
    return _stream_slots


def _client_ip(request: web.Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote or "?"


# ------------------------------------------------- tiny TTL cache for MongoDB
_cache: dict = {}


async def _cached(key, loader):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < SETTINGS_CACHE_TTL:
        return hit[1]
    value = await loader()
    _cache[key] = (now, value)
    if len(_cache) > 20000:
        _cache.clear()
    return value


async def _check_expiry(file_id: int, secure_hash: str = None):
    """Return a 410 response if the link has expired, else None (fail-open on any problem)."""
    try:
        expiry_seconds = await _cached("link_expiry", db.get_link_expiry)
        if expiry_seconds and expiry_seconds > 0:
            # Match on message id AND hash, newest first: ids from another bot / channel that
            # share this MongoDB must never make a fresh link look old.
            query = {"file_id": file_id}
            if secure_hash:
                query["hash"] = secure_hash
            rec = await _cached(
                ("file", file_id, secure_hash),
                lambda: db.files.find_one(query, sort=[("timestamp", -1)]),
            )
            ts = (rec or {}).get("timestamp")
            if ts:
                age = time.time() - float(ts)
                if age > expiry_seconds:
                    log.info("link %s expired: age %.0fs > limit %ss", file_id, age, expiry_seconds)
                    return web.Response(
                        status=410,
                        text=(f"🚫 This link has expired.\n"
                              f"Link age: {int(age // 60)} min, allowed: {int(expiry_seconds // 60)} min.\n"
                              f"Please request a new link from the bot."),
                    )
    except Exception:
        log.warning("expiry check failed (ignored)", exc_info=True)
    return None


def _parse_path(request: web.Request):
    path = request.match_info["path"]
    m = PATH_RE.match(path)
    if m:
        return int(m.group(2)), m.group(1)
    m = re.search(r"(\d+)(?:\/\S+)?", path)
    if not m:
        raise web.HTTPBadRequest(text="Bad link")
    return int(m.group(1)), request.rel_url.query.get("hash")


# ------------------------------------------------------------------ routes
@routes.get("/", allow_head=True)
async def root_route_handler(_):
    return web.json_response({
        "server_status": "running",
        "uptime": get_readable_time(time.time() - StartTime),
        "telegram_bot": "@" + BOT_USERNAME,
        "connected_bots": len(multi_clients),
        "loads": {f"bot{i}": load for i, load in sorted(work_loads.items())},
        "active_streams": active_streams(),
        "active_lanes": active_lanes(),
        "waiting": _waiting,
        "served_mb": round(STATS["bytes"] / 1048576, 1),
        "cache": diskcache.info(),
        "cpu": memguard.cpu_info(),
        "memory_mb": round(memguard.rss_mb()),
        "memory_limit_mb": memguard.limit_mb(),
        "errors": STATS["errors"],
        "retries": STATS["retries"],
        "version": __version__,
    })


@routes.get("/health", allow_head=True)
async def health_handler(_):
    return web.json_response({"ok": True})


@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def stream_watch_handler(request: web.Request):
    try:
        if not multi_clients:
            return web.Response(status=503, text="Bot is starting, retry in a few seconds")
        id, secure_hash = _parse_path(request)
        expired = await _check_expiry(id, secure_hash)
        if expired:
            return expired
        return web.Response(text=await render_page(id, secure_hash), content_type="text/html")
    except web.HTTPException:
        raise
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        return web.Response(status=400, text="Bad Request")
    except Exception as e:
        log.exception("watch page error")
        return web.Response(status=500, text="Internal error, please retry")


@routes.get(r"/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        id, secure_hash = _parse_path(request)
        expired = await _check_expiry(id, secure_hash)
        if expired:
            return expired
        return await media_streamer(request, id, secure_hash)
    except web.HTTPException:
        raise
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except ConnectionResetError:
        log.info("client disconnected: %s", request.path)
        return web.Response(status=400, text="Client disconnected")
    except (AttributeError, BadStatusLine):
        log.exception("bad request / internal attribute error on %s", request.path)
        return web.Response(status=400, text="Bad Request")
    except Exception:
        log.exception("stream error")
        return web.Response(status=500, text="Internal error, please retry")


def _parse_range(header: str, file_size: int):
    """Returns (from_bytes, until_bytes) or None when unsatisfiable. Supports a-b, a-, -n."""
    m = RANGE_RE.match(header.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        raise ValueError("bad range")
    if m.group(1) == "":                       # suffix: last n bytes
        n = int(m.group(2))
        if n <= 0:
            return None
        return max(0, file_size - n), file_size - 1
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else file_size - 1
    end = min(end, file_size - 1)              # browsers may ask beyond EOF
    if start >= file_size or end < start:
        return None
    return start, end


def _content_disposition(name: str) -> str:
    safe = name.replace('"', "'").replace("\r", " ").replace("\n", " ")
    ascii_name = safe.encode("ascii", "ignore").decode() or "file"
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(name)}"


async def media_streamer(request: web.Request, id: int, secure_hash: str):
    global _waiting

    if not multi_clients:
        return web.Response(status=503, text="Bot is starting, retry in a few seconds")

    # ---- pick the least loaded client and read the file properties
    index = pick_client_index()
    streamer = get_byte_streamer(multi_clients[index])
    file_id = await streamer.get_file_properties(id)

    if not secure_hash or file_id.unique_id[:6] != secure_hash:
        raise InvalidHash

    file_size = int(file_id.file_size or 0)
    is_head = request.method == "HEAD"
    range_header = request.headers.get("Range")

    from_bytes, until_bytes = 0, file_size - 1
    partial = False
    if range_header and file_size > 0:
        try:
            parsed = _parse_range(range_header, file_size)
        except ValueError:
            parsed = (0, file_size - 1)         # malformed header -> ignore, serve full file
        else:
            partial = parsed is not None
        if parsed is None:
            return web.Response(
                status=416, text="416: Range Not Satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        from_bytes, until_bytes = parsed

    req_length = max(0, until_bytes - from_bytes + 1)
    mime_type = file_id.mime_type or "application/octet-stream"
    file_name = file_id.file_name or f"{secrets.token_hex(2)}.bin"

    headers = {
        "Content-Type": mime_type,
        "Content-Length": str(req_length),
        "Content-Disposition": _content_disposition(file_name),
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    }
    if partial:
        headers["Content-Range"] = f"bytes {from_bytes}-{until_bytes}/{file_size}"

    status = 206 if partial else 200
    if is_head or req_length == 0:
        return web.Response(status=status, headers=headers)

    # ---- admission control: protects RAM / bandwidth when many users arrive
    if memguard.pressure() > MEM_SHED_RATIO:
        memguard.trim()
        return web.Response(status=503, text="Server memory is full, please retry in a few seconds",
                            headers={"Retry-After": "5"})
    ip = request.headers.get("CF-Connecting-IP") or _client_ip(request)
    if MAX_STREAMS_PER_IP and _per_ip.get(ip, 0) >= MAX_STREAMS_PER_IP:
        return web.Response(status=429, text="Too many parallel downloads from your IP",
                            headers={"Retry-After": "5"})
    sem = _slots()
    _waiting += 1
    try:
        await asyncio.wait_for(sem.acquire(), STREAM_QUEUE_TIMEOUT)
    except asyncio.TimeoutError:
        return web.Response(status=503, text="Server is busy, please retry in a moment",
                            headers={"Retry-After": "10"})
    finally:
        _waiting -= 1
    _per_ip[ip] = _per_ip.get(ip, 0) + 1

    try:
        # ---- stream geometry
        offset, first_part_cut, last_part_cut, part_count = compute_geometry(
            from_bytes, until_bytes, CHUNK_SIZE
        )

        cache_entry = diskcache.acquire(f"{id}_{file_id.unique_id[:6]}", file_size)

        def make_stream():
            if cache_entry is not None:
                return diskcache.serve(cache_entry, from_bytes, until_bytes, (index, file_id, id))
            return stream_file(
                index, file_id, id, offset, first_part_cut, last_part_cut, part_count, CHUNK_SIZE
            )

        response = web.StreamResponse(status=status, headers=headers)
        sent = 0
        prepared = False
        failure = None

        # one transparent retry if the stream breaks before the first byte
        for attempt in range(2):
            try:
                async with aclosing(make_stream()) as gen:
                    it = gen.__aiter__()
                    while True:
                        try:
                            chunk = await asyncio.wait_for(it.__anext__(), STALL_TIMEOUT)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            raise ConnectionError(f"upstream stalled for {STALL_TIMEOUT}s")
                        if not prepared:
                            await response.prepare(request)
                            prepared = True
                        await response.write(chunk)
                        sent += len(chunk)
                failure = None
                break
            except (ConnectionResetError, asyncio.CancelledError) as e:
                # the client (or the proxy in front of us, e.g. a Cloudflare Worker) went away
                log.info("peer closed after %.1f of %.1f MB (id=%s range=%s) via %s",
                         sent / 1048576, req_length / 1048576, id, range_header or "-", type(e).__name__)
                raise
            except Busy:
                return web.Response(status=503, text="Server is busy, please retry in a moment",
                                    headers={"Retry-After": "10"})
            except Exception as e:
                if request.transport is None or request.transport.is_closing():
                    log.info("peer closed after %.1f of %.1f MB (id=%s) while writing: %r",
                             sent / 1048576, req_length / 1048576, id, e)
                    return response            # client disconnected mid-stream
                failure = e
                if sent == 0 and attempt == 0:
                    log.warning("stream failed before first byte (%r), retrying once", e)
                    with suppress(Exception):
                        await streamer.get_file_properties(id, refresh=True)
                    continue
                break

        if failure is not None:
            log.error("stream aborted after %s/%s bytes: %r", sent, req_length, failure)
            if not prepared:
                return web.Response(status=502, text="Upstream error, please retry")
            # tell the client the body is incomplete (it can resume with Range)
            if request.transport is not None:
                request.transport.close()
            return response

        if not prepared:  # empty generator (should not happen)
            await response.prepare(request)
        with suppress(ConnectionResetError, RuntimeError):
            await response.write_eof()
        return response

    except (ConnectionResetError, asyncio.CancelledError):
        raise
    finally:
        diskcache.release(locals().get("cache_entry"))
        sem.release()
        left = _per_ip.get(ip, 1) - 1
        if left <= 0:
            _per_ip.pop(ip, None)
        else:
            _per_ip[ip] = left
