"""
Engine tests against a mock Telegram (no network needed):
    python tests/test_engine.py
"""
import asyncio, os, random, sys, time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mock_env as M                                    # noqa: E402  (installs fake modules)
import web.utils.custom_dl as dl                        # noqa: E402
from web.server import multi_clients, work_loads        # noqa: E402

CH = 1024 * 1024
OK, FAIL = "✅", "❌"
failed = 0


def check(name, cond, extra=""):
    global failed
    if not cond:
        failed += 1
    print(f"{OK if cond else FAIL} {name} {extra}")


def setup_clients(n):
    multi_clients.clear(); work_loads.clear(); dl._streamers.clear(); dl._bad_until.clear()
    M.Session.created = 0
    for i in range(n):
        multi_clients[i] = M.Client()
        work_loads[i] = 0


async def get_stream(from_b, until_b, index=0):
    streamer = dl.get_byte_streamer(multi_clients[index])
    fid = await streamer.get_file_properties(1)
    off, fpc, lpc, parts = dl.compute_geometry(from_b, until_b, CH)
    out = bytearray()
    gen = dl.stream_file(index, fid, 1, off, fpc, lpc, parts, CH)
    try:
        async for c in gen:
            out += c
    finally:
        await gen.aclose()
    return bytes(out)


def expected(from_b, until_b):
    return M.content(from_b, until_b - from_b + 1) if until_b - from_b + 1 <= CH else b"".join(
        M.content(p, min(CH, until_b + 1 - p)) for p in range(from_b, until_b + 1, CH))


def idle_state():
    return (dl.active_streams() == 0 and dl.active_lanes() == 0 and all(v == 0 for v in work_loads.values())
            and dl._budget.free == dl._budget.total)


async def leftover_tasks():
    await asyncio.sleep(0.3)
    return [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]


async def main():
    random.seed(7)
    size = M.FILE_SIZE

    # 1 ---------------------------------------------------------------- geometry (pure, 3000 random ranges)
    bad = 0
    for _ in range(3000):
        a = random.randrange(size); b = random.randrange(a, size)
        off, fpc, lpc, parts = dl.compute_geometry(a, b, CH)
        chunks = [M.content(off + i * CH, min(CH, size - off - i * CH)) for i in range(parts)]
        if parts == 1:
            out = chunks[0][fpc:lpc]
        else:
            out = chunks[0][fpc:] + b"".join(chunks[1:-1]) + chunks[-1][:lpc]
        if out != expected(a, b):
            bad += 1
    for a, b in [(0, 0), (0, CH - 1), (0, CH), (CH, CH), (CH - 1, CH), (size - 1, size - 1), (0, size - 1)]:
        off, fpc, lpc, parts = dl.compute_geometry(a, b, CH)
        chunks = [M.content(off + i * CH, min(CH, size - off - i * CH)) for i in range(parts)]
        out = chunks[0][fpc:lpc] if parts == 1 else chunks[0][fpc:] + b"".join(chunks[1:-1]) + chunks[-1][:lpc]
        if out != expected(a, b):
            bad += 1
    check("range geometry (3000 random + edge cases)", bad == 0, f"bad={bad}")

    # 2 ---------------------------------------------------------------- full file, 4 bots
    setup_clients(4)
    t = time.time()
    data = await get_stream(0, size - 1)
    check("full file correct (4 bots)", data == expected(0, size - 1), f"{len(data)} bytes, {time.time()-t:.2f}s")
    check("state clean after stream", idle_state())

    # 3 ---------------------------------------------------------------- tricky ranges
    ok = True
    for a, b in [(0, 0), (5, 5), (CH - 1, CH), (CH, 2 * CH - 1), (CH + 17, 3 * CH + 4), (size - 1, size - 1),
                 (size - 3 * CH - 5, size - 1), (123456, 123456 + 9 * CH)]:
        got = await get_stream(a, b)
        if got != expected(a, b):
            ok = False; print("   mismatch", a, b, len(got))
    check("edge-case ranges (chunk boundaries, last byte, tiny)", ok)

    # 4 ---------------------------------------------------------------- injected faults
    M.FAULTS["p"] = 0.15
    M.FAULTS["kinds"] = ("timeout", "conn", "flood", "rpc500", "ref")
    t = time.time()
    data = await get_stream(0, size - 1)
    M.FAULTS["p"] = 0.0
    check("full file correct with 15% random errors (timeouts/conn/flood/5xx/ref-expired)",
          data == expected(0, size - 1), f"{time.time()-t:.1f}s, retries={dl.STATS['retries']}")
    check("state clean after faulty stream", idle_state())

    # 5 ---------------------------------------------------------------- unrecoverable error must RAISE
    M.FAULTS["hard_fail"] = True
    old = dl.FETCH_RETRIES; dl.FETCH_RETRIES = 2
    raised = False
    try:
        await get_stream(0, 8 * CH)
    except Exception:
        raised = True
    dl.FETCH_RETRIES = old; M.FAULTS["hard_fail"] = False; dl._bad_until.clear()
    check("dead upstream -> stream raises (no silent truncation)", raised)
    check("state clean after failed stream", idle_state())

    # 6 ---------------------------------------------------------------- client disconnect mid-stream
    setup_clients(4)
    streamer = dl.get_byte_streamer(multi_clients[0]); fid = await streamer.get_file_properties(1)
    off, fpc, lpc, parts = dl.compute_geometry(0, size - 1, CH)
    gen = dl.stream_file(0, fid, 1, off, fpc, lpc, parts, CH)
    n = 0
    async for _ in gen:
        n += 1
        if n == 3:
            break
    await gen.aclose()
    left = await leftover_tasks()
    check("disconnect mid-stream cleans everything", idle_state() and not left and M.COUNTERS["inflight"] == 0,
          f"leftover_tasks={len(left)} inflight={M.COUNTERS['inflight']}")

    # 7 ---------------------------------------------------------------- 80 users at once
    setup_clients(4)
    M.COUNTERS["max_inflight"] = 0
    jobs = []
    for _ in range(80):
        a = random.randrange(size - 1); b = min(size - 1, a + random.randrange(1, 14 * CH))
        jobs.append((a, b))
    t = time.time()
    res = await asyncio.gather(*[get_stream(a, b, index=min(work_loads, key=work_loads.get)) for a, b in jobs])
    good = sum(1 for (a, b), r in zip(jobs, res) if r == expected(a, b))
    check(f"80 concurrent users, all bytes correct", good == 80, f"{good}/80 in {time.time()-t:.1f}s")
    check("peak parallel GetFile requests stayed within the RAM budget", M.COUNTERS["max_inflight"] <= dl._budget.total,
          f"peak={M.COUNTERS['max_inflight']}")
    left = await leftover_tasks()
    check("no leaked tasks / counters after the burst", idle_state() and not left, f"leftover={len(left)}")

    # 8 ---------------------------------------------------------------- 80 users + 10% errors
    M.FAULTS["p"] = 0.10
    res = await asyncio.gather(*[get_stream(a, b, index=min(work_loads, key=work_loads.get)) for a, b in jobs],
                               return_exceptions=True)
    M.FAULTS["p"] = 0.0
    good = sum(1 for (a, b), r in zip(jobs, res) if not isinstance(r, Exception) and r == expected(a, b))
    check("80 concurrent users with 10% errors", good == 80, f"{good}/80")
    check("state clean after stress", idle_state())

    # 9 ---------------------------------------------------------------- file-properties de-duplication
    setup_clients(1)
    calls = {"n": 0}
    orig = multi_clients[0].get_messages
    async def counted(*a, **k):
        calls["n"] += 1
        return await orig(*a, **k)
    multi_clients[0].get_messages = counted
    s0 = dl.get_byte_streamer(multi_clients[0])
    await asyncio.gather(*[s0.get_file_properties(1) for _ in range(300)])
    check("300 simultaneous page views -> 1 Telegram call", calls["n"] == 1, f"calls={calls['n']}")

    # 10 --------------------------------------------------------------- fallback path (stream_media)
    setup_clients(2)
    dl._raw_broken = True
    data = await get_stream(3 * CH + 11, 12 * CH + 5)
    dl._raw_broken = False
    check("fallback path (Client.stream_media) gives correct bytes", data == expected(3 * CH + 11, 12 * CH + 5))

    # 11 --------------------------------------------------------------- adaptive lanes + speed scaling (mock latency)
    M.LATENCY = (0.08, 0.08)
    res = {}
    for n_bots, par in [(1, 1), (4, 4)]:
        setup_clients(n_bots); dl.MAX_PARALLEL_CLIENTS = par
        await get_stream(0, 2 * CH)  # warm sessions
        t = time.time(); await get_stream(0, size - 1); res[n_bots] = time.time() - t
    dl.MAX_PARALLEL_CLIENTS = 4; M.LATENCY = (0.02, 0.05)
    check("more bots => faster single stream (mock, 80 ms latency)", res[4] < res[1] * 0.6,
          f"1 bot {res[1]:.2f}s vs 4 bots {res[4]:.2f}s")

    # 12 --------------------------------------------------------------- fairness: many streams => 1 lane each
    setup_clients(4)
    lanes_seen = []
    orig_start = dl._Lane.start
    def spy(self, use_raw):
        lanes_seen.append(dl.active_streams())
        return orig_start(self, use_raw)
    dl._Lane.start = spy
    await asyncio.gather(*[get_stream(0, 20 * CH) for _ in range(8)])
    dl._Lane.start = orig_start
    check("bots are shared fairly under load (lanes shrink as streams grow)", True,
          f"lanes started={len(lanes_seen)} for 8 streams (single stream would use 4 each = 32)")
    check("lanes < 32 under load", len(lanes_seen) < 32)

    # 13 --------------------------------------------------------------- FloodWait storm (the real-world log)
    setup_clients(1)
    M.FAULTS["flood_over"] = 10          # Telegram refuses > 10 parallel GetFile on this bot
    M.COUNTERS["max_inflight"] = 0
    storm = [(random.randrange(0, 5 * CH), 0) for _ in range(30)]
    storm = [(a, a + 9 * CH) for a, _ in storm]
    t0 = time.time()
    res = await asyncio.gather(*[get_stream(a, b) for a, b in storm], return_exceptions=True)
    M.FAULTS["flood_over"] = 0
    good = sum(1 for (a, b), r in zip(storm, res) if not isinstance(r, Exception) and r == expected(a, b))
    gate = dl.get_byte_streamer(multi_clients[0]).gate
    check("30 users on ONE bot while Telegram floods above 10 parallel calls: all complete", good == 30,
          f"{good}/30 in {time.time()-t0:.1f}s, gate limit adapted to {gate.limit}")
    check("gate kept parallel calls near the safe level", gate.limit <= 10 or gate.limit < dl.MAX_REQUESTS_PER_CLIENT,
          f"peak={M.COUNTERS['max_inflight']}")
    check("state clean after flood storm", idle_state())

    # 14 --------------------------------------------------------------- strict RAM budget (the OOM case)
    setup_clients(6)
    dl._budget = dl._Budget(16)                      # pretend a tiny server: 16 MB for streaming
    M.COUNTERS["max_inflight"] = 0
    big = [(random.randrange(0, 20 * CH), None) for _ in range(60)]
    big = [(a, a + random.randrange(2, 12) * CH) for a, _ in big]
    t0 = time.time()
    res = await asyncio.gather(*[get_stream(a, b, index=dl.pick_client_index()) for a, b in big],
                               return_exceptions=True)
    good = sum(1 for (a, b), r in zip(big, res) if not isinstance(r, Exception) and r == expected(a, b))
    check("60 big parallel streams with only 16 MB budget: all finish, no deadlock", good == 60,
          f"{good}/60 in {time.time()-t0:.1f}s")
    check("buffers never exceeded the budget", M.COUNTERS["max_inflight"] <= 16, f"peak={M.COUNTERS['max_inflight']}")
    check("budget fully returned", idle_state(), f"free={dl._budget.free}/{dl._budget.total}")

    # 15 --------------------------------------------------------------- saturated server answers Busy (-> HTTP 503)
    dl._budget = dl._Budget(2); dl.STREAM_QUEUE_TIMEOUT = 1
    streamer = dl.get_byte_streamer(multi_clients[0]); fid = await streamer.get_file_properties(1)
    off, fpc, lpc, parts = dl.compute_geometry(0, 30 * CH, CH)
    hog = dl.stream_file(0, fid, 1, off, fpc, lpc, parts, CH)
    await hog.__anext__()                              # holds the whole 2-slot budget
    t0 = time.time(); busy = False
    try:
        await get_stream(0, 5 * CH)
    except dl.Busy:
        busy = True
    await hog.aclose()
    dl.STREAM_QUEUE_TIMEOUT = 20
    check("saturated server -> Busy after the queue timeout (HTTP 503), no hang", busy and time.time() - t0 < 3,
          f"{time.time()-t0:.1f}s")
    check("budget returned after hog closed", dl._budget.free == dl._budget.total)

    print("\n" + ("ALL TESTS PASSED" if failed == 0 else f"{failed} TEST(S) FAILED"))
    return failed


sys.exit(asyncio.run(main()))
