"""
Fake Telegram / pyrogram layer used ONLY by tests/test_engine.py.
Lets us exercise the real web/utils/custom_dl.py without network access.
"""
import asyncio, os, random, sys, types
from types import SimpleNamespace

os.environ.update(API_ID="1", API_HASH="x", BOT_TOKEN="1:x", BIN_CHANNEL="-100123", DATABASE_URI="x")

PAT = bytes(range(251)) * 4400          # > 1 MB + 251


def content(off: int, n: int) -> bytes:
    r = off % 251
    return PAT[r:r + n]


FILE_SIZE = 37 * 1024 * 1024 + 12345     # not a multiple of 1 MB
FAULTS = {"flood_over": 0, "p": 0.0, "kinds": ("timeout", "conn", "flood", "rpc500"), "hard_fail": False}
COUNTERS = {"inflight": 0, "max_inflight": 0, "calls": 0, "ref_expired_once": set()}
LATENCY = (0.02, 0.05)


class FloodWait(Exception):
    value = 1


class RPCErr500(Exception):
    CODE = 500


class FileReferenceExpired(Exception):
    CODE = 400


class AuthBytesInvalid(Exception):
    pass


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


# ---- raw -------------------------------------------------------------
class GetFile:
    def __init__(self, location, offset, limit):
        self.location, self.offset, self.limit = location, offset, limit


class File:
    def __init__(self, bytes_):
        self.bytes = bytes_


class InputDocumentFileLocation:
    def __init__(self, **kw):
        self.__dict__.update(kw)


raw = _mod("pyrogram.raw")
raw.functions = _mod("pyrogram.raw.functions")
raw.functions.upload = _mod("pyrogram.raw.functions.upload", GetFile=GetFile)
raw.functions.auth = _mod("pyrogram.raw.functions.auth",
                          ExportAuthorization=lambda dc_id: SimpleNamespace(dc_id=dc_id),
                          ImportAuthorization=lambda id, bytes: SimpleNamespace())
raw.types = _mod("pyrogram.raw.types", InputDocumentFileLocation=InputDocumentFileLocation,
                 InputPhotoFileLocation=InputDocumentFileLocation,
                 InputPeerPhotoFileLocation=InputDocumentFileLocation,
                 InputPeerUser=InputDocumentFileLocation, InputPeerChat=InputDocumentFileLocation,
                 InputPeerChannel=InputDocumentFileLocation)
raw.types.upload = _mod("pyrogram.raw.types.upload", File=File)
_mod("pyrogram.raw.types.messages", Messages=object)


# ---- file_id ---------------------------------------------------------
class FileType:
    CHAT_PHOTO, PHOTO, DOCUMENT = 1, 2, 3


class ThumbnailSource:
    CHAT_PHOTO_BIG = 1


class FileId:
    dc_id = 4
    file_type = FileType.DOCUMENT
    media_id = 1
    access_hash = 1
    file_reference = b"ref"
    thumbnail_size = ""

    @classmethod
    def decode(cls, s):
        return cls()


_mod("pyrogram.file_id", FileId=FileId, FileType=FileType, ThumbnailSource=ThumbnailSource)


# ---- session ---------------------------------------------------------
class Session:
    created = 0

    def __init__(self, client, dc_id, auth_key, test_mode, is_media=False):
        self.dc_id = dc_id
        self.is_started = asyncio.Event()
        Session.created += 1

    async def start(self):
        self.is_started.set()

    async def stop(self):
        self.is_started.clear()

    async def restart(self):
        pass

    async def send(self, req, *a, **k):
        if isinstance(req, GetFile):
            COUNTERS["calls"] += 1
            COUNTERS["inflight"] += 1
            COUNTERS["max_inflight"] = max(COUNTERS["max_inflight"], COUNTERS["inflight"])
            try:
                if FAULTS["flood_over"] and COUNTERS["inflight"] > FAULTS["flood_over"]:
                    raise FloodWait()          # like Telegram: too many parallel GetFile -> FLOOD_WAIT
                await asyncio.sleep(random.uniform(*LATENCY))
                if FAULTS["hard_fail"]:
                    raise ConnectionError("dead")
                if random.random() < FAULTS["p"]:
                    kind = random.choice(FAULTS["kinds"])
                    if kind == "timeout":
                        raise TimeoutError("Request timed out")
                    if kind == "conn":
                        raise ConnectionError("Connection lost")
                    if kind == "flood":
                        raise FloodWait()
                    if kind == "rpc500":
                        raise RPCErr500()
                    if kind == "ref":
                        raise FileReferenceExpired()
                if req.offset >= FILE_SIZE:
                    return File(b"")
                n = min(req.limit, FILE_SIZE - req.offset)
                return File(content(req.offset, n))
            finally:
                COUNTERS["inflight"] -= 1
        return SimpleNamespace()


class Auth:
    def __init__(self, *a):
        pass

    async def create(self):
        return b"k"


_mod("pyrogram.session", Session=Session, Auth=Auth)
_mod("pyrogram.errors", AuthBytesInvalid=AuthBytesInvalid, FloodWait=FloodWait)


# ---- client ----------------------------------------------------------
class _Storage:
    async def test_mode(self): return False
    async def dc_id(self): return 2
    async def auth_key(self): return b"k"


class Client:
    def __init__(self, *a, **kw):
        self.media_sessions = {}
        self.storage = _Storage()

    async def invoke(self, req):
        return SimpleNamespace(id=1, bytes=b"x")

    async def get_messages(self, chat_id, id):
        await asyncio.sleep(0.01)
        doc = SimpleNamespace(file_id="FID", file_unique_id="UNIQ123456", file_size=FILE_SIZE,
                              mime_type="video/mp4", file_name="t.mp4")
        return SimpleNamespace(empty=False, document=doc)

    async def stream_media(self, ref, offset=0, limit=0):
        pos = offset * 1024 * 1024
        n = 0
        while pos < FILE_SIZE and (limit == 0 or n < limit):
            await asyncio.sleep(0.01)
            yield content(pos, min(1024 * 1024, FILE_SIZE - pos))
            pos += 1024 * 1024
            n += 1


class _Types(types.ModuleType):
    Message = object


pg = _mod("pyrogram", Client=Client, raw=raw, idle=lambda: None, enums=SimpleNamespace(), filters=SimpleNamespace())
pg.types = _mod("pyrogram.types", Message=object)
pg.utils = _mod("pyrogram.utils", get_channel_id=lambda x: x)
pg.file_id = sys.modules["pyrogram.file_id"]

# ---- heavy third-party modules that are not installed here -----------
for name in ("aiohttp", "pytz", "motor", "motor.motor_asyncio", "aiofiles", "shortzy", "dns"):
    if name not in sys.modules:
        try:
            __import__(name)
        except Exception:
            sys.modules[name] = types.ModuleType(name)
sys.modules["motor.motor_asyncio"].AsyncIOMotorClient = lambda *a, **k: SimpleNamespace(
    __getitem__=lambda s, k: SimpleNamespace())
db_mod = _mod("database.users_db", db=SimpleNamespace(), mydb=SimpleNamespace(bot_sessions=None))
sys.modules.setdefault("database", types.ModuleType("database"))
sys.modules["database"].users_db = db_mod
aio = sys.modules["aiohttp"]
aio.ClientSession = object
aio.ClientTimeout = lambda **k: None
sys.modules["pytz"].timezone = lambda x: None

# ---- minimal aiohttp.web stub (only so modules import; real aiohttp is used in production) ----
class _Routes:
    def get(self, *a, **k):
        return lambda f: f


class _HTTPExc(Exception):
    def __init__(self, text=None, **k):
        self.text = text


web_stub = _mod("aiohttp.web",
                RouteTableDef=_Routes, Request=object, Response=lambda **k: SimpleNamespace(**k),
                StreamResponse=object, HTTPException=_HTTPExc,
                HTTPForbidden=type("HTTPForbidden", (_HTTPExc,), {}),
                HTTPNotFound=type("HTTPNotFound", (_HTTPExc,), {}),
                HTTPBadRequest=type("HTTPBadRequest", (_HTTPExc,), {}),
                Application=object, json_response=lambda *a, **k: None, middleware=lambda f: f)
aio.web = web_stub
aio.http_exceptions = _mod("aiohttp.http_exceptions", BadStatusLine=type("BadStatusLine", (Exception,), {}))
