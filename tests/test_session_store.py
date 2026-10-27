"""python tests/test_session_store.py  -- stored logins + FloodWait helper (fake MongoDB)"""
import asyncio, os, sys, types
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mock_env  # noqa: F401

class FakeCol:
    def __init__(self): self.d = {}
    async def find_one(self, q): return self.d.get(q["_id"])
    async def update_one(self, q, u, upsert=False): self.d.setdefault(q["_id"], {"_id": q["_id"]}).update(u["$set"])
    async def delete_one(self, q): self.d.pop(q["_id"], None)

import session_store as S
S._col = FakeCol()

class FakeClient:
    async def export_session_string(self): return "SESSION-STRING"

class FloodWait(Exception):
    value = 1748

async def main():
    tok = "12345:AAAbbb"
    assert await S.load(tok) is None
    await S.save(tok, FakeClient())
    assert await S.load(tok) == "SESSION-STRING"
    assert await S.load("12345:other") == "SESSION-STRING"          # keyed by bot id
    await S.forget(tok)
    assert await S.load(tok) is None
    assert S.is_flood(FloodWait()) == 1748 and S.is_flood(ValueError()) == 0
    print("\u2705 session store: save / load / forget / flood detection")

asyncio.run(main())
