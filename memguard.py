"""
Memory guard for small hosts (Koyeb free = 512 MB): detects the container limit, tells the
HTTP layer when memory is nearly full (so it answers 503 instead of getting OOM-killed),
and hands freed memory back to the OS.
"""
import asyncio
import gc
import logging
import os
import time

log = logging.getLogger("mem")

try:
    import psutil
    _proc = psutil.Process()
except Exception:  # pragma: no cover
    psutil = None
    _proc = None

_CGROUP_FILES = ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")
_cache = {"t": 0.0, "rss": 0.0}


def limit_mb():
    """Container memory limit in MB (env MEMORY_LIMIT_MB wins), or None when unknown/unlimited."""
    env = os.environ.get("MEMORY_LIMIT_MB", "").strip()
    if env.isdigit() and int(env) > 0:
        return float(env)
    for path in _CGROUP_FILES:
        try:
            with open(path) as f:
                v = f.read().strip()
            if v.isdigit() and int(v) < (1 << 50):      # a huge number means "unlimited"
                return int(v) / 1048576
        except OSError:
            pass
    return None


def rss_mb() -> float:
    now = time.monotonic()
    if now - _cache["t"] < 0.5:
        return _cache["rss"]
    val = 0.0
    try:
        if _proc is not None:
            val = _proc.memory_info().rss / 1048576
        else:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        val = int(line.split()[1]) / 1024
                        break
    except Exception:
        pass
    _cache.update(t=now, rss=val)
    return val


def pressure() -> float:
    """Used / limit (0.0 when the limit is unknown)."""
    lim = limit_mb()
    return rss_mb() / lim if lim else 0.0


def trim() -> None:
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


async def trimmer(interval: int = 20):
    """Background job: periodically return freed memory to the OS; hurry when memory is tight."""
    while True:
        p = pressure()
        await asyncio.sleep(3 if p > 0.8 else interval)
        before = rss_mb()
        trim()
        _cache["t"] = 0.0
        after = rss_mb()
        if p > 0.8:
            log.warning("memory %.0f MB (%.0f%% of limit) - trimmed %.0f MB", after, 100 * p, before - after)
