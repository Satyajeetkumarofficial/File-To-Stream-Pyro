"""python tests/test_expiry.py -- link expiry check (fake MongoDB)"""
import asyncio, os, sys, time
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mock_env  # noqa: F401
import web.stream_routes as sr

NOW = time.time()


class FakeFiles:
    def __init__(self, rows): self.rows = rows
    async def find_one(self, q, sort=None):
        hits = [r for r in self.rows if all(r.get(k) == v for k, v in q.items())]
        if sort: hits.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return hits[0] if hits else None


class FakeDB:
    def __init__(self, expiry, rows): self.expiry, self.files = expiry, FakeFiles(rows)
    async def get_link_expiry(self): return self.expiry


async def check(expiry, rows, fid=2071, h="AgAD7y"):
    sr._cache.clear(); sr.db = FakeDB(expiry, rows)
    return await sr._check_expiry(fid, h)


async def main():
    fresh = {"file_id": 2071, "hash": "AgAD7y", "timestamp": NOW - 30}
    old_other_bot = {"file_id": 2071, "hash": "ZZZZZZ", "timestamp": NOW - 86400}
    assert await check(600, [fresh]) is None
    assert await check(600, [old_other_bot, fresh]) is None, "stale record of another bot must not expire a fresh link"
    assert await check(600, [fresh, old_other_bot]) is None
    r = await check(600, [{"file_id": 2071, "hash": "AgAD7y", "timestamp": NOW - 3600}])
    assert r is not None and r.status == 410 and "60 min" in r.text and "10 min" in r.text, getattr(r, "text", r)
    assert await check(0, [{"file_id": 2071, "hash": "AgAD7y", "timestamp": NOW - 99999}]) is None   # expiry off
    assert await check(600, []) is None                                                              # unknown file: fail-open
    assert await check(600, [{"file_id": 2071, "hash": "AgAD7y"}]) is None                          # record without timestamp
    print("\u2705 expiry: fresh link never expires early, collisions ignored, real expiry gives 410 with age/limit, off = never")

asyncio.run(main())
