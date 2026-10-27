"""python tests/test_diskcache.py -- disk cache against the mock Telegram"""
import asyncio, os, random, shutil, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mock_env as M                                   # noqa: E402
import web.utils.custom_dl as dl                       # noqa: E402
import web.utils.diskcache as dc                       # noqa: E402
from web.server import multi_clients, work_loads       # noqa: E402

CH = 1024 * 1024
failed = 0
tmp = tempfile.mkdtemp(prefix="cachetest_")
dc.DISK_CACHE_DIR = tmp


def check(name, cond, extra=""):
    global failed
    failed += 0 if cond else 1
    print(("✅" if cond else "❌"), name, extra)


def expected(a, b):
    return b"".join(M.content(p, min(CH, b + 1 - p)) for p in range(a, b + 1, CH))


def setup(n=4, limit_mb=200):
    multi_clients.clear(); work_loads.clear(); dl._streamers.clear(); dl._bad_until.clear()
    for e in list(dc._entries.values()):
        dc._drop(e)
    dc.LIMIT = limit_mb * CH
    for i in range(n):
        multi_clients[i] = M.Client(); work_loads[i] = 0


async def read(key, a, b, size=M.FILE_SIZE):
    entry = dc.acquire(key, size)
    assert entry is not None
    fid = await dl.get_byte_streamer(multi_clients[0]).get_file_properties(1)
    out = bytearray()
    gen = dc.serve(entry, a, b, (0, fid, 1))
    try:
        async for c in gen:
            out += c
    finally:
        await gen.aclose()
        dc.release(entry)
    return bytes(out)


async def main():
    random.seed(3)
    size = M.FILE_SIZE
    setup()
    t = time.time()
    data = await read("f1", 0, size - 1)
    check("first read correct (fetched + cached)", data == expected(0, size - 1), f"{time.time()-t:.2f}s")
    calls = M.COUNTERS["calls"]
    t = time.time()
    data = await read("f1", 0, size - 1)
    check("second read correct and served from disk with ZERO Telegram calls",
          data == expected(0, size - 1) and M.COUNTERS["calls"] == calls, f"{time.time()-t:.2f}s")

    ok = True
    for a, b in [(0, 0), (5, 5), (CH - 1, CH), (CH + 17, 3 * CH + 4), (size - 1, size - 1), (123456, 123456 + 9 * CH)]:
        if await read("f1", a, b) != expected(a, b):
            ok = False
    check("edge-case ranges from cache", ok)

    # many readers of a NEW file, random ranges, concurrent: Telegram asked ~once per part
    setup()
    M.COUNTERS["calls"] = 0
    jobs = []
    for _ in range(40):
        a = random.randrange(0, size - 1); b = min(size - 1, a + random.randrange(1, 15 * CH)); jobs.append((a, b))
    res = await asyncio.gather(*[read("f2", a, b) for a, b in jobs])
    good = sum(1 for (a, b), r in zip(jobs, res) if r == expected(a, b))
    parts_total = -(-size // CH)
    check("40 concurrent overlapping readers: all bytes correct", good == 40, f"{good}/40")
    check("Telegram fetched each part at most ~once (dedupe)", M.COUNTERS["calls"] <= parts_total + 25,
          f"calls={M.COUNTERS['calls']} parts={parts_total}")

    # faults during fill
    setup()
    M.FAULTS["p"] = 0.15; M.FAULTS["kinds"] = ("timeout", "conn", "rpc500", "ref")
    data = await read("f3", 0, size - 1)
    M.FAULTS["p"] = 0.0
    check("fill survives 15% random upstream errors", data == expected(0, size - 1))

    # hard failure then recovery
    setup()
    M.FAULTS["hard_fail"] = True; old = dl.FETCH_RETRIES; dl.FETCH_RETRIES = 2
    dl.STREAM_QUEUE_TIMEOUT = 20
    raised = False
    try:
        await read("f4", 0, 6 * CH)
    except Exception:
        raised = True
    M.FAULTS["hard_fail"] = False; dl.FETCH_RETRIES = old; dl._bad_until.clear()
    ent = dc._entries["f4"]
    check("dead upstream -> reader gets an error", raised)
    check("failed parts are not marked cached / nothing left pending", sum(ent.have) == 0 and not ent.pending)
    check("same file works again after recovery", await read("f4", 0, 6 * CH) == expected(0, 6 * CH))

    # eviction + bypass
    setup(limit_mb=100)
    for k in ("a", "b"):
        e = dc.acquire(k, 40 * CH); dc.release(e)
    e = dc.acquire("c", 40 * CH); dc.release(e)       # needs space -> evicts oldest idle ("a")
    check("LRU eviction of idle files", "a" not in dc._entries and "c" in dc._entries and "b" in dc._entries,
          f"entries={list(dc._entries)}")
    check("file larger than the cache bypasses it", dc.acquire("huge", 200 * CH) is None)
    e1 = dc.acquire("b", 40 * CH); e2 = dc.acquire("c", 40 * CH)       # both in use
    check("no room and nothing idle -> bypass (no error)", dc.acquire("d", 40 * CH) is None)
    dc.release(e1); dc.release(e2)

    # disconnect mid-read: no leaks
    setup()
    entry = dc.acquire("f5", size)
    fid = await dl.get_byte_streamer(multi_clients[0]).get_file_properties(1)
    gen = dc.serve(entry, 0, size - 1, (0, fid, 1))
    n = 0
    async for _ in gen:
        n += 1
        if n == 3:
            break
    await gen.aclose(); dc.release(entry)
    await asyncio.sleep(1.5)
    left = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    check("disconnect mid-read: fill jobs finish, nothing leaks",
          not left and entry.runs == 0 and dl.active_streams() == 0 and dl._budget.free == dl._budget.total,
          f"tasks={len(left)} runs={entry.runs}")
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("ALL CACHE TESTS PASSED" if failed == 0 else f"{failed} FAILED"))
    return failed

sys.exit(asyncio.run(main()))
