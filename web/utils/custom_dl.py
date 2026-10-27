"""
Streaming engine for the File-to-Link bot (Pyrofork / Hydrogram / Pyrogram-fork compatible).

Design goals: stable speed, no half-sent files, many simultaneous users.

* Every stream is split into "lanes" (striped: lane k fetches parts k, k+n, k+2n...).
  A lane is ONE bot client / ONE Telegram media connection, with a sliding
  window of GetFile requests in flight, so all lanes prefetch simultaneously.
* Lane count is ADAPTIVE: with a single active stream it uses up to
  MAX_PARALLEL_CLIENTS bots (max speed); as more users stream, each stream
  gets fewer lanes so the bots are shared fairly (stable under load).
* Memory is BOUNDED: a lane never holds more than `window` chunks, and the
  window shrinks when many lanes are active (MAX_INFLIGHT_CHUNKS ~= max MB).
* Every GetFile call has retries (FloodWait, timeouts, 5xx, broken media
  session, expired file reference). If a chunk finally cannot be fetched the
  stream raises, so the HTTP layer aborts the connection and the client can
  resume with a Range request instead of silently receiving a truncated file.
* If the low-level (raw Session) path is unavailable in the installed
  library version, it automatically falls back to `Client.stream_media()`.
"""
import asyncio
import logging
import time
from collections import OrderedDict, deque
from contextlib import suppress
from typing import Dict, List, Optional

from info import (
    BIN_CHANNEL,
    FETCH_RETRIES,
    FETCH_TIMEOUT,
    FILE_CACHE_SIZE,
    FLOOD_BUDGET,
    MAX_FLOOD_SLEEP,
    MAX_INFLIGHT_CHUNKS,
    MAX_PARALLEL_CLIENTS,
    MAX_REQUESTS_PER_CLIENT,
    MIN_PARTS_PER_WORKER,
    MIN_REQUESTS_PER_CLIENT,
    PREFETCH_WINDOW,
    STREAM_QUEUE_TIMEOUT,
)
from web.server import work_loads, multi_clients
from web.server.exceptions import FIleNotFound
from .file_properties import get_file_ids

from pyrogram import Client, utils, raw
from pyrogram.file_id import FileId, FileType, ThumbnailSource

try:  # low-level media sessions (fast path)
    from pyrogram.session import Session, Auth
    from pyrogram.errors import AuthBytesInvalid
    _RAW_OK = True
except Exception:  # pragma: no cover - depends on library version
    Session = Auth = None  # type: ignore
    AuthBytesInvalid = Exception  # type: ignore
    _RAW_OK = False
    logging.warning("Raw media sessions unavailable, using Client.stream_media() fallback")

log = logging.getLogger("streamer")

# ----------------------------------------------------------------------------
# Patch: serialise Session.restart() per Session instance (Pyrogram can fire
# several internal restarts at once when a connection drops, which ends in
# "RuntimeError: read() called while another coroutine is already waiting").
# ----------------------------------------------------------------------------
if _RAW_OK and not getattr(Session, "_restart_patched", False):
    try:
        _original_session_restart = Session.restart

        async def _locked_session_restart(self, *args, **kwargs):
            lock = self.__dict__.get("_custom_restart_lock")
            if lock is None:
                lock = asyncio.Lock()
                self.__dict__["_custom_restart_lock"] = lock
            async with lock:
                return await _original_session_restart(self, *args, **kwargs)

        Session.restart = _locked_session_restart
        Session._restart_patched = True
    except Exception:  # pragma: no cover
        log.warning("Could not patch Session.restart()", exc_info=True)

# ----------------------------------------------------------------------------
# Global (process wide) counters
# ----------------------------------------------------------------------------
_active_streams = 0
_active_lanes = 0
STATS = {"bytes": 0, "streams_total": 0, "errors": 0, "retries": 0, "started": time.time()}

_FILE_REF_ERRORS = {"FileReferenceExpired", "FileReferenceInvalid", "FileReferenceEmpty"}
_SESSION_ERRORS = {"AuthBytesInvalid", "AuthKeyUnregistered", "AuthKeyInvalid", "AuthKeyDuplicated"}
_PROPS_TTL = 20 * 60  # seconds a cached file_reference is trusted


def active_streams() -> int:
    return _active_streams


def active_lanes() -> int:
    return _active_lanes


def _flood_seconds(exc: Exception) -> int:
    return int(getattr(exc, "value", None) or getattr(exc, "x", None) or 1)


# ---- circuit breaker: a client that keeps failing is skipped for a while ----
_bad_until: Dict[int, float] = {}
_BAD_SECONDS = 45


def mark_bad(idx: int) -> None:
    if len(multi_clients) > 1:
        _bad_until[idx] = time.time() + _BAD_SECONDS
        log.warning("Client %s marked unhealthy for %ss", idx, _BAD_SECONDS)


def healthy_clients() -> List[tuple]:
    now = time.time()
    items = [kv for kv in multi_clients.items() if _bad_until.get(kv[0], 0) <= now]
    return items or list(multi_clients.items())


def pick_client_index() -> int:
    """Least-loaded healthy client."""
    items = healthy_clients()
    return min((i for i, _ in items), key=lambda i: work_loads.get(i, 0))


# ============================================================================
# Per-bot request gate (adaptive): protects a bot from FLOOD_WAIT storms
# ============================================================================
class _Gate:
    """
    * limits simultaneous GetFile calls of ONE bot (AIMD: halves on FloodWait,
      +1 after every 25 successes, between MIN and MAX_REQUESTS_PER_CLIENT)
    * on FloodWait pauses ALL requests of that bot until the wait is over, so
      dozens of lanes do not retry at the same instant (thundering herd).
    """

    def __init__(self):
        self.limit = MAX_REQUESTS_PER_CLIENT
        self.inflight = 0
        self.paused_until = 0.0
        self._ok = 0
        self._last_cut = 0.0
        self._waiters: deque = deque()

    def _wake(self):
        room = max(1, self.limit - self.inflight)
        while self._waiters and room > 0:
            w = self._waiters.popleft()
            if not w.done():
                w.set_result(None)
                room -= 1

    async def acquire(self):
        loop = asyncio.get_running_loop()
        while True:
            now = time.monotonic()
            if now >= self.paused_until and self.inflight < self.limit:
                self.inflight += 1
                return
            fut = loop.create_future()
            self._waiters.append(fut)
            timeout = (self.paused_until - now) if now < self.paused_until else None
            try:
                await asyncio.wait_for(fut, timeout)
            except asyncio.TimeoutError:
                pass
            finally:
                with suppress(ValueError):
                    self._waiters.remove(fut)

    def release(self):
        self.inflight = max(0, self.inflight - 1)
        self._wake()

    def success(self):
        self._ok += 1
        if self._ok >= 25 and self.limit < MAX_REQUESTS_PER_CLIENT:
            self.limit += 1
            self._ok = 0
            self._wake()

    def flood(self, seconds: float) -> bool:
        """Register a FloodWait. Returns True when this is a NEW event (for logging)."""
        now = time.monotonic()
        new_event = now >= self.paused_until
        self.paused_until = max(self.paused_until, now + seconds + 0.2)
        if now - self._last_cut > 2:
            self.limit = max(MIN_REQUESTS_PER_CLIENT, int(self.limit * 0.6))
            self._last_cut = now
            self._ok = 0
        return new_event


# ============================================================================
# ByteStreamer: per-client cache of file properties + media sessions
# ============================================================================
class ByteStreamer:
    def __init__(self, client: Client):
        self.client: Client = client
        self._props: "OrderedDict[int, tuple]" = OrderedDict()  # id -> (ts, FileId)
        self._inflight: Dict[int, asyncio.Task] = {}
        self._session_locks: Dict[int, asyncio.Lock] = {}
        self.gate = _Gate()

    # ---------------------------------------------------------------- props
    def _cache_get(self, id: int) -> Optional[FileId]:
        item = self._props.get(id)
        if item is None:
            return None
        ts, fid = item
        if time.time() - ts > _PROPS_TTL:
            self._props.pop(id, None)
            return None
        self._props.move_to_end(id)
        return fid

    def _cache_put(self, id: int, fid: FileId) -> None:
        self._props[id] = (time.time(), fid)
        self._props.move_to_end(id)
        while len(self._props) > FILE_CACHE_SIZE:
            self._props.popitem(last=False)

    def seed(self, id: int, fid: FileId) -> None:
        """Store properties that were already fetched by the caller."""
        if self._cache_get(id) is None:
            self._cache_put(id, fid)

    async def _load(self, id: int) -> FileId:
        fid = await get_file_ids(self.client, BIN_CHANNEL, id)
        if not fid:
            raise FIleNotFound
        self._cache_put(id, fid)
        return fid

    async def get_file_properties(self, id: int, refresh: bool = False) -> FileId:
        """Cached + de-duplicated: 500 users opening one link = 1 Telegram call."""
        if not refresh:
            hit = self._cache_get(id)
            if hit is not None:
                return hit
        task = self._inflight.get(id)
        if task is None:
            task = asyncio.create_task(self._load(id))
            self._inflight[id] = task

            def _done(t: asyncio.Task, _id=id):
                self._inflight.pop(_id, None)
                if not t.cancelled():
                    t.exception()  # mark retrieved, avoids "never retrieved" warnings

            task.add_done_callback(_done)
        return await asyncio.shield(task)

    # -------------------------------------------------------- media sessions
    def _lock(self, dc_id: int) -> asyncio.Lock:
        return self._session_locks.setdefault(dc_id, asyncio.Lock())

    async def generate_media_session(self, client: Client, file_id: FileId) -> "Session":
        """Media session for the DC that stores the file (one per client+DC)."""
        async with self._lock(file_id.dc_id):
            media_session = client.media_sessions.get(file_id.dc_id)

            if media_session is not None:
                started = getattr(media_session, "is_started", None)
                if started is not None and hasattr(started, "is_set") and not started.is_set():
                    # dead session left behind - rebuild it
                    client.media_sessions.pop(file_id.dc_id, None)
                    with suppress(Exception):
                        await asyncio.wait_for(media_session.stop(), 10)
                    media_session = None

            if media_session is None:
                test_mode = await client.storage.test_mode()
                if file_id.dc_id != await client.storage.dc_id():
                    media_session = Session(
                        client,
                        file_id.dc_id,
                        await Auth(client, file_id.dc_id, test_mode).create(),
                        test_mode,
                        is_media=True,
                    )
                    await media_session.start()

                    for _ in range(6):
                        exported_auth = await client.invoke(
                            raw.functions.auth.ExportAuthorization(dc_id=file_id.dc_id)
                        )
                        try:
                            await media_session.send(
                                raw.functions.auth.ImportAuthorization(
                                    id=exported_auth.id, bytes=exported_auth.bytes
                                )
                            )
                            break
                        except AuthBytesInvalid:
                            continue
                    else:
                        await media_session.stop()
                        raise AuthBytesInvalid
                else:
                    media_session = Session(
                        client,
                        file_id.dc_id,
                        await client.storage.auth_key(),
                        test_mode,
                        is_media=True,
                    )
                    await media_session.start()
                client.media_sessions[file_id.dc_id] = media_session
                log.debug("Created media session for DC %s", file_id.dc_id)
            return media_session

    async def renew_media_session(self, client: Client, file_id: FileId, bad: "Session") -> "Session":
        """Drop `bad` (only if nobody replaced it yet) and return a healthy session."""
        async with self._lock(file_id.dc_id):
            cur = client.media_sessions.get(file_id.dc_id)
            if cur is not None and cur is bad:
                client.media_sessions.pop(file_id.dc_id, None)
                with suppress(Exception):
                    await asyncio.wait_for(bad.stop(), 10)
        return await self.generate_media_session(client, file_id)

    # ------------------------------------------------------------- location
    @staticmethod
    async def get_location(file_id: FileId):
        file_type = file_id.file_type

        if file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id, access_hash=file_id.chat_access_hash
                )
            else:
                if file_id.chat_access_hash == 0:
                    peer = raw.types.InputPeerChat(chat_id=-file_id.chat_id)
                else:
                    peer = raw.types.InputPeerChannel(
                        channel_id=utils.get_channel_id(file_id.chat_id),
                        access_hash=file_id.chat_access_hash,
                    )
            return raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
        if file_type == FileType.PHOTO:
            return raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )
        return raw.types.InputDocumentFileLocation(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
            thumb_size=file_id.thumbnail_size,
        )


_streamers: Dict[Client, ByteStreamer] = {}


def get_byte_streamer(client: Client) -> ByteStreamer:
    s = _streamers.get(client)
    if s is None:
        s = _streamers[client] = ByteStreamer(client)
    return s


# ============================================================================
# One lane = one client + one contiguous range of parts
# ============================================================================
class _Lane:
    """
    One client + the parts it is responsible for. Parts are STRIPED across lanes
    (lane k gets parts k, k+n, k+2n ...), so while the consumer reads part i from
    lane i % n, all lanes keep prefetching ahead at the same time.
    """

    def __init__(self, idx: int, client: Client, file_row: int, parts: List[int],
                 offset: int, chunk_size: int, window: int):
        self.idx = idx
        self.client = client
        self.streamer = get_byte_streamer(client)
        self.id = file_row
        self.parts = parts
        self.count = len(parts)
        self.offset = offset
        self.chunk_size = chunk_size
        self.window = window
        self.slots = asyncio.Semaphore(window)       # back-pressure
        self.queue: asyncio.Queue = asyncio.Queue()  # ordered futures/tasks
        self.tasks: List[asyncio.Future] = []
        self.runner: Optional[asyncio.Task] = None
        self.file_id: Optional[FileId] = None
        self.location = None
        self.session = None

    # ----------------------------------------------------------------- fetch
    async def _setup(self):
        self.file_id = await self.streamer.get_file_properties(self.id)
        self.location = await self.streamer.get_location(self.file_id)
        self.session = await self.streamer.generate_media_session(self.client, self.file_id)

    async def _renew_session(self):
        self.session = await self.streamer.renew_media_session(
            self.client, self.file_id, self.session
        )

    async def _fetch(self, off: int) -> bytes:
        gate = self.streamer.gate
        last: Optional[BaseException] = None
        attempt = 0
        flood_left = FLOOD_BUDGET
        while attempt < FETCH_RETRIES:
            action = None
            await gate.acquire()
            try:
                r = await asyncio.wait_for(
                    self.session.send(
                        raw.functions.upload.GetFile(
                            location=self.location, offset=off, limit=self.chunk_size
                        )
                    ),
                    FETCH_TIMEOUT,
                )
                gate.success()
                return r.bytes if isinstance(r, raw.types.upload.File) else b""
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last = e
                name = type(e).__name__
                STATS["retries"] += 1
                if name in ("FloodWait", "FloodPremiumWait"):
                    wait = _flood_seconds(e)
                    if gate.flood(wait):
                        log.warning("FloodWait %ss on client %s -> pausing it, limit now %s",
                                    wait, self.idx, gate.limit)
                    flood_left -= wait
                    if wait > MAX_FLOOD_SLEEP or flood_left < 0:
                        raise
                    continue          # does not use a retry; the gate holds everyone back
                attempt += 1
                if name in _FILE_REF_ERRORS:
                    action = ("ref", 0)
                elif isinstance(e, (asyncio.TimeoutError, TimeoutError)) or getattr(e, "CODE", 0) >= 500:
                    # NOTE: checked before OSError because TimeoutError is an OSError
                    action = ("renew" if attempt >= 2 else "sleep", min(0.3 * (2 ** attempt), 3))
                elif name in _SESSION_ERRORS or isinstance(e, (ConnectionError, OSError, RuntimeError)):
                    action = ("renew", min(0.3 * (2 ** attempt), 3))
                else:
                    raise
            finally:
                gate.release()

            # recovery happens OUTSIDE the gate so it never blocks other requests
            kind, delay = action
            if kind == "ref":
                self.file_id = await self.streamer.get_file_properties(self.id, refresh=True)
                self.location = await self.streamer.get_location(self.file_id)
            elif kind == "renew":
                await self._renew_session()
            if delay:
                await asyncio.sleep(delay)
        raise last if last else RuntimeError("fetch failed")

    # --------------------------------------------------------------- runners
    async def _push_error(self, exc: BaseException):
        fut = asyncio.get_running_loop().create_future()
        fut.set_exception(exc)
        fut.exception()  # silence "never retrieved" if the consumer is already gone
        await self.queue.put(fut)

    async def _run_raw(self):
        try:
            await self._setup()
            for p in self.parts:
                await self.slots.acquire()
                t = asyncio.ensure_future(self._fetch(self.offset + p * self.chunk_size))
                self.tasks.append(t)
                await self.queue.put(t)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._push_error(e)
        finally:
            await self.queue.put(None)

    async def _run_fallback(self):
        """Client.stream_media() path (sequential, but always compatible)."""
        try:
            fid = await self.streamer.get_file_properties(self.id)
            ref = getattr(fid, "file_id_str", None)
            if not ref:
                raise RuntimeError("file_id_str missing for fallback streaming")
            start_chunk = (self.offset // self.chunk_size) + self.parts[0]  # contiguous (single lane)
            async for chunk in self.client.stream_media(ref, offset=start_chunk, limit=self.count):
                await self.slots.acquire()
                fut = asyncio.get_running_loop().create_future()
                fut.set_result(chunk)
                await self.queue.put(fut)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._push_error(e)
        finally:
            await self.queue.put(None)

    def start(self, use_raw: bool):
        self.runner = asyncio.create_task(self._run_raw() if use_raw else self._run_fallback())

    async def close(self):
        pending = [t for t in self.tasks if not t.done()]
        if self.runner and not self.runner.done():
            pending.append(self.runner)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for t in self.tasks:  # retrieve exceptions of finished-but-unused tasks
            if t.done() and not t.cancelled():
                t.exception()


def compute_geometry(from_bytes: int, until_bytes: int, chunk_size: int = 1024 * 1024):
    """Byte range (inclusive) -> (offset, first_part_cut, last_part_cut, part_count)."""
    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1
    part_count = until_bytes // chunk_size - offset // chunk_size + 1
    return offset, first_part_cut, last_part_cut, part_count


class Busy(Exception):
    """Server is saturated: no buffer budget became free in time (HTTP layer answers 503)."""


class _Budget:
    """
    Strict global pool of 1 MB chunk slots. A stream reserves ALL of its slots at once
    (lanes x window) before it starts and gives them back when it ends, so the RAM used by
    streaming can never exceed `total` MB, and there is no hold-and-wait deadlock.
    """

    def __init__(self, total: int):
        self.total = total
        self.free = total
        self._waiters: deque = deque()

    async def reserve(self, want_lanes: int, want_window: int, streams: int, timeout: float):
        loop = asyncio.get_running_loop()
        deadline = time.monotonic() + timeout
        while True:
            if self.free >= 1:
                # fair share: no single stream may swallow the pool while others are active
                cap = max(2, min(self.free, self.total // max(1, streams)))
                cap = min(cap, self.free)
                lanes = max(1, min(want_lanes, cap // 2 if cap >= 2 else 1))
                window = max(min(2, want_window), min(want_window, cap // lanes))
                tokens = lanes * window
                if tokens <= self.free:
                    self.free -= tokens
                    return lanes, window, tokens
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Busy
            fut = loop.create_future()
            self._waiters.append(fut)
            try:
                await asyncio.wait_for(fut, remaining)
            except asyncio.TimeoutError:
                raise Busy
            finally:
                with suppress(ValueError):
                    self._waiters.remove(fut)

    def release(self, tokens: int):
        self.free = min(self.total, self.free + tokens)
        while self._waiters:
            w = self._waiters.popleft()
            if not w.done():
                w.set_result(None)


_budget = _Budget(MAX_INFLIGHT_CHUNKS)


# ============================================================================
# Public generator used by the HTTP layer
# ============================================================================
_raw_broken = False


async def stream_file(
    primary_index: int,
    primary_file_id: FileId,
    id: int,
    offset: int,
    first_part_cut: int,
    last_part_cut: int,
    part_count: int,
    chunk_size: int,
):
    """
    Yield the bytes of `part_count` parts starting at `offset`
    (first part trimmed by first_part_cut, last part by last_part_cut).
    Raises on unrecoverable failure so the caller can abort the connection.
    """
    global _active_streams, _active_lanes, _raw_broken

    _active_streams += 1
    STATS["streams_total"] += 1
    lanes: List[_Lane] = []
    reserved = 0
    try:
        # ---- choose clients: least loaded first, primary first on ties
        ordered = sorted(
            healthy_clients(),
            key=lambda kv: (work_loads.get(kv[0], 0), 0 if kv[0] == primary_index else 1),
        )
        n_clients = len(ordered)
        fair = max(1, n_clients // max(1, _active_streams))
        n_workers = max(
            1,
            min(MAX_PARALLEL_CLIENTS, n_clients, fair, max(1, part_count // MIN_PARTS_PER_WORKER)),
        )
        chosen = ordered[:n_workers]

        # the primary client's properties were fetched by the caller already
        for cidx, client in chosen:
            if cidx == primary_index:
                get_byte_streamer(client).seed(id, primary_file_id)

        use_raw = _RAW_OK and not _raw_broken
        if not use_raw:                       # stream_media() can only read contiguous ranges
            n_workers = 1
            chosen = chosen[:1]

        want_window = max(1, min(PREFETCH_WINDOW, -(-part_count // n_workers)))
        got_lanes, window, tokens = await _budget.reserve(
            n_workers, want_window, _active_streams, STREAM_QUEUE_TIMEOUT
        )
        reserved = tokens
        n_workers = got_lanes
        chosen = chosen[:n_workers]

        for w, (cidx, client) in enumerate(chosen):
            parts = list(range(w, part_count, n_workers)) if use_raw else list(range(part_count))
            if not parts:
                continue
            lanes.append(_Lane(cidx, client, id, parts, offset, chunk_size, window))
            _active_lanes += 1
            work_loads[cidx] = work_loads.get(cidx, 0) + 1

        for lane in lanes:
            lane.start(use_raw)

        # ---- consume parts strictly in order (part i comes from lane i % n)
        n_lanes = len(lanes)
        for global_part in range(part_count):
            lane = lanes[global_part % n_lanes]
            item = await lane.queue.get()
            if item is None:
                raise ConnectionError(f"Lane {lane.idx} ended early at part {global_part}/{part_count}")
            try:
                chunk = await item
            except Exception as e:
                mark_bad(lane.idx)
                if use_raw and isinstance(e, (AttributeError, TypeError, ImportError, NotImplementedError)):
                    _raw_broken = True
                    log.error("Raw streaming path broken (%r) - switching to fallback", e)
                raise
            if not chunk:
                raise ConnectionError("Telegram returned an empty chunk before EOF")

            if part_count == 1:
                out = chunk[first_part_cut:last_part_cut]
            elif global_part == 0:
                out = chunk[first_part_cut:]
            elif global_part == part_count - 1:
                out = chunk[:last_part_cut]
            else:
                out = chunk

            STATS["bytes"] += len(out)
            yield out
            lane.slots.release()
    except Exception:
        STATS["errors"] += 1
        raise
    finally:
        for lane in lanes:
            await lane.close()
            _active_lanes = max(0, _active_lanes - 1)
            work_loads[lane.idx] = max(0, work_loads.get(lane.idx, 1) - 1)
        if reserved:
            _budget.release(reserved)
        _active_streams = max(0, _active_streams - 1)


# Backwards compatible name used by older code
parallel_yield_file = stream_file
