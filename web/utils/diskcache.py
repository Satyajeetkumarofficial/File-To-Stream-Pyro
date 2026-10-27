"""
Disk cache for streamed files (uses storage to buy speed and stability).

* One sparse file per Telegram file; a bitmap says which 1 MB parts are on disk.
* A reader asks for parts in order; missing parts are fetched by the normal streaming engine
  (multi-bot lanes, retries, RAM budget) in "fill runs" that look `CACHE_READAHEAD` parts ahead.
* Several readers of the same file share the same pending parts: Telegram is asked once.
* Files already on disk are served without touching Telegram at all.
* LRU eviction of idle files; a file that does not fit simply bypasses the cache.
* Any disk problem -> acquire() returns None and the caller streams directly (never an error).
"""
import asyncio
import logging
import os
import shutil
import time
from collections import OrderedDict
from contextlib import aclosing
from typing import Dict, Optional

from info import CACHE_MAX_RUNS, CACHE_READAHEAD, DISK_CACHE_DIR, DISK_CACHE_MB, STALL_TIMEOUT
from web.utils.custom_dl import Busy, compute_geometry, stream_file

log = logging.getLogger("cache")
CH = 1024 * 1024

LIMIT = DISK_CACHE_MB * CH
STATS = {"hits_parts": 0, "fetched_parts": 0, "evictions": 0, "bypass": 0}
_entries: "OrderedDict[str, _Entry]" = OrderedDict()
_reserved = 0
_ready = False


class _Entry:
    def __init__(self, key: str, size: int, path: str, fd: int):
        self.key, self.size, self.path, self.fd = key, size, path, fd
        self.nparts = -(-size // CH)
        self.have = bytearray(self.nparts)
        self.pending: Dict[int, asyncio.Future] = {}
        self.refs = 0
        self.runs = 0
        self.last = time.monotonic()
        self.ctx = None  # (client_index, FileId, message_id) used by fill runs

    def idle(self) -> bool:
        return self.refs == 0 and self.runs == 0


def enabled() -> bool:
    return LIMIT > 0


def _init() -> bool:
    global _ready
    if _ready:
        return True
    try:
        shutil.rmtree(DISK_CACHE_DIR, ignore_errors=True)   # leftovers of a previous run
        os.makedirs(DISK_CACHE_DIR, exist_ok=True)
        _ready = True
    except OSError as e:
        log.warning("disk cache unavailable: %r", e)
    return _ready


def _drop(entry: _Entry):
    global _reserved
    _entries.pop(entry.key, None)
    _reserved -= entry.size
    try:
        os.close(entry.fd)
    except OSError:
        pass
    try:
        os.unlink(entry.path)
    except OSError:
        pass


def acquire(key: str, size: int) -> Optional[_Entry]:
    """Entry for this file (created if needed) or None when it cannot be cached."""
    global _reserved
    if not enabled() or size <= 0 or size > LIMIT * 0.9 or not _init():
        STATS["bypass"] += 1
        return None
    entry = _entries.get(key)
    if entry is None:
        for victim in list(_entries.values()):                # oldest first
            if _reserved + size <= LIMIT:
                break
            if victim.idle():
                log.info("cache: evicting %s (%.0f MB)", victim.key, victim.size / CH)
                _drop(victim)
                STATS["evictions"] += 1
        if _reserved + size > LIMIT:
            STATS["bypass"] += 1
            return None
        path = os.path.join(DISK_CACHE_DIR, key.replace("/", "_"))
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o600)
            os.ftruncate(fd, size)
        except OSError as e:
            log.warning("cache: cannot create %s: %r", path, e)
            STATS["bypass"] += 1
            return None
        entry = _Entry(key, size, path, fd)
        _entries[key] = entry
        _reserved += size
    _entries.move_to_end(key)
    entry.refs += 1
    entry.last = time.monotonic()
    return entry


def release(entry: Optional[_Entry]):
    if entry is not None:
        entry.refs = max(0, entry.refs - 1)
        entry.last = time.monotonic()


def _fail(entry: _Entry, a: int, b: int, exc: BaseException):
    for q in range(a, b):
        fut = entry.pending.pop(q, None)
        if fut is not None and not fut.done():
            fut.set_exception(exc)
            fut.exception()  # silence "never retrieved" when nobody is waiting


async def _fill(entry: _Entry, a: int, b: int):
    """Fetch parts [a, b) with the normal engine and write them to disk."""
    entry.runs += 1
    index, file_id, mid = entry.ctx
    p = a
    try:
        last_byte = min(b * CH, entry.size) - 1
        off, fpc, lpc, parts = compute_geometry(a * CH, last_byte, CH)
        async with aclosing(stream_file(index, file_id, mid, off, fpc, lpc, parts, CH)) as gen:
            async for chunk in gen:
                await asyncio.to_thread(os.pwrite, entry.fd, chunk, p * CH)
                entry.have[p] = 1
                STATS["fetched_parts"] += 1
                fut = entry.pending.pop(p, None)
                if fut is not None and not fut.done():
                    fut.set_result(None)
                p += 1
        if p != b:
            raise ConnectionError(f"short fill {p}/{b}")
    except asyncio.CancelledError as e:
        _fail(entry, p, b, ConnectionError("fill cancelled"))
        raise
    except BaseException as e:  # Busy, ConnectionError, OSError ...
        if not isinstance(e, Busy):
            log.warning("cache fill %s [%s,%s) failed at %s: %r", entry.key, a, b, p, e)
        _fail(entry, p, b, e)
    finally:
        entry.runs -= 1


def _schedule(entry: _Entry, start: int, end: int):
    """Start fill runs for the missing, not yet pending parts of [start, end)."""
    p = start
    while p < end and entry.runs < CACHE_MAX_RUNS:
        if entry.have[p] or p in entry.pending:
            p += 1
            continue
        q = p
        while q < end and not entry.have[q] and q not in entry.pending:
            q += 1
        loop = asyncio.get_running_loop()
        for x in range(p, q):
            entry.pending[x] = loop.create_future()
        task = asyncio.create_task(_fill(entry, p, q))
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        p = q


async def serve(entry: _Entry, from_bytes: int, until_bytes: int, ctx):
    """Yield bytes [from_bytes, until_bytes] (inclusive), fetching missing parts on demand."""
    entry.ctx = entry.ctx or ctx
    first, last = from_bytes // CH, until_bytes // CH
    for p in range(first, last + 1):
        # look ahead: start a fill run when the next missing part is close
        window_end = min(entry.nparts, p + CACHE_READAHEAD)
        q = p
        while q < window_end and (entry.have[q] or q in entry.pending):
            q += 1
        if q < window_end and q - p <= CACHE_READAHEAD // 2:
            _schedule(entry, q, window_end)

        if not entry.have[p]:
            deadline = time.monotonic() + STALL_TIMEOUT
            while not entry.have[p]:
                fut = entry.pending.get(p)
                if fut is None:                       # no free fill slot yet: try again shortly
                    _schedule(entry, p, min(entry.nparts, p + CACHE_READAHEAD))
                    if time.monotonic() > deadline:
                        raise ConnectionError("cache fill did not start in time")
                    await asyncio.sleep(0.02)
                    continue
                await asyncio.wait_for(asyncio.shield(fut), max(1.0, deadline - time.monotonic()))
        else:
            STATS["hits_parts"] += 1

        start = max(from_bytes, p * CH) - p * CH
        end = min(until_bytes, (p + 1) * CH - 1) - p * CH + 1
        data = await asyncio.to_thread(os.pread, entry.fd, end - start, p * CH + start)
        if len(data) != end - start:
            raise OSError("cache read returned fewer bytes than expected")
        entry.last = time.monotonic()
        yield data


def info() -> dict:
    return {
        "enabled": enabled(),
        "limit_mb": LIMIT // CH,
        "files": len(_entries),
        "reserved_mb": _reserved // CH,
        "cached_mb": sum(sum(e.have) for e in _entries.values()),
        **STATS,
    }
