from os import environ, getenv
from Script import script
from memguard import limit_mb as _limit_mb, cpu_limit as _cpu_limit


# ───────────────────────── safe env helpers ─────────────────────────
def _env_bool(name: str, default: bool) -> bool:
    """'False' / '0' / 'no' / 'off' / '' are really False (plain environ.get() is not)."""
    val = environ.get(name)
    if val is None:
        return default
    val = str(val).strip().lower()
    if val == "":
        return default
    return val in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int = 0) -> int:
    """Never crashes on missing / malformed numbers."""
    try:
        return int(str(environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _required(name: str) -> str:
    val = environ.get(name, "").strip()
    if not val:
        raise SystemExit(f"❌ Missing required environment variable: {name}")
    return val


# 🚀 __Bot Configuration__
SESSION = environ.get('SESSION', 'ProBotz')  # Session name
API_ID = int(_required('API_ID'))
API_HASH = _required('API_HASH')
BOT_TOKEN = _required('BOT_TOKEN')

# 🚫 __Non Streaming Channels__
NO_STREAM_CHANNELS = [int(i) for i in environ.get("NO_STREAM_CHANNELS", "-1002269651634, -1001887894502").replace(",", " ").split()]

# 👑 __Owner & Admins__
ADMINS = [int(i) for i in environ.get('ADMINS', '7413682152').split()]
AUTH_CHANNEL = [int(i) for i in environ.get("AUTH_CHANNEL", "-1002269651634").replace(",", " ").split()]
OWNER_USERNAME = environ.get("OWNER_USERNAME", 'SatyajeetKumarOfficial')
BOT_USERNAME = environ.get("BOT_USERNAME", 'QuickFile2LinkProBot')

# 🔗 __Channel & Support Links__
CHANNEL = environ.get('CHANNEL', 'https://t.me/ProBotXUpdate')
SUPPORT = environ.get('SUPPORT', 'https://t.me/ProBotUpdate')
HOW_TO_VERIFY = environ.get('HOW_TO_VERIFY', 'https://t.me/ProBotUpdate')
HOW_TO_OPEN = environ.get('HOW_TO_OPEN', 'https://t.me/ProBotUpdate')

# 📢 __Log Channels__
BIN_CHANNEL = int(_required("BIN_CHANNEL"))
LOG_CHANNEL = _env_int("LOG_CHANNEL", 0)
PREMIUM_LOGS = _env_int("PREMIUM_LOGS", 0)
VERIFIED_LOG = _env_int('VERIFIED_LOG', 0)
SUPPORT_GROUP = _env_int("SUPPORT_GROUP", 0)

# ✅ __Feature Toggles__
VERIFY = False  # Enable user verification
FSUB = _env_bool("FSUB", True)  # Force Subscribe
ENABLE_LIMIT = _env_bool("ENABLE_LIMIT", True)
BATCH_VERIFY = False
IS_SHORTLINK = False
MAINTENANCE_MODE = _env_bool("MAINTENANCE_MODE", False)
PROTECT_CONTENT = _env_bool('PROTECT_CONTENT', False)
PUBLIC_FILE_STORE = _env_bool('PUBLIC_FILE_STORE', True)
BATCH_PROTECT_CONTENT = _env_bool('BATCH_PROTECT_CONTENT', False)

# 🔗 __Shortlink Configuration__
SHORTLINK_URL = environ.get('SHORTLINK_URL', '')
SHORTLINK_API = environ.get('SHORTLINK_API', '')

# 💾 __Database Configuration__
DB_URL = environ.get('DATABASE_URI', "")
DB_NAME = environ.get('DATABASE_NAME', "ProBotz")

# 📸 __Media & Images__
QR_CODE = environ.get('QR_CODE', 'https://ibb.co/h1DVpLfR')
VERIFY_IMG = environ.get("VERIFY_IMG", "https://ibb.co/h1DVpLfR")
AUTH_PICS = environ.get('AUTH_PICS', 'https://ibb.co/h1DVpLfR')
PICS = environ.get('PICS', 'https://ibb.co/h1DVpLfR')
FILE_PIC = environ.get('FILE_PIC', 'https://ibb.co/h1DVpLfR')

# 📝 __Captions__
FILE_CAPTION = environ.get('FILE_CAPTION', script.CAPTION)
BATCH_FILE_CAPTION = environ.get('BATCH_FILE_CAPTION', script.CAPTION)
CHANNEL_FILE_CAPTION = environ.get('CHANNEL_FILE_CAPTION', script.CAPTION)

# ⏱️ __Time & Limits__
PING_INTERVAL = _env_int("PING_INTERVAL", 1200)
SLEEP_THRESHOLD = _env_int('SLEEP_THRESHOLD', 60)
RATE_LIMIT_TIMEOUT = _env_int("RATE_LIMIT_TIMEOUT", 600)
MAX_FILES = _env_int("MAX_FILES", 50)
VERIFY_EXPIRE = _env_int('VERIFY_EXPIRE', 90)  # Hours

# ⚙️ __Worker & App Config__
WORKERS = _env_int('WORKERS', 50)
MULTI_CLIENT = True
NAME = environ.get('name', 'ProBotz')



# ───────────────────── memory-aware defaults ─────────────────────
MEMORY_LIMIT_MB = _limit_mb()          # None = unknown / unlimited
CPU_LIMIT = _cpu_limit()               # vCPUs, None = unknown / unlimited
SLOW_CPU = CPU_LIMIT is not None and CPU_LIMIT < 0.5   # e.g. Koyeb free = 0.1 vCPU


def _auto(small, mid, big):
    """Pick a default by container size: <=640 MB / <=1.25 GB / bigger (unknown -> mid)."""
    m = MEMORY_LIMIT_MB
    if m is None:
        return mid
    return small if m <= 640 else (mid if m <= 1280 else big)

# 🚀 __Streaming / Speed / Stability tuning__ (all optional, safe defaults)
# GetFile requests kept in flight per worker. 4-6 is the sweet spot.
PREFETCH_WINDOW = max(1, _env_int("PREFETCH_WINDOW", 5))
# Max bot accounts (MULTI_TOKEN*) used in parallel for ONE stream.
# Automatically reduced when many users stream at once (fair sharing).
MAX_PARALLEL_CLIENTS = max(1, _env_int("MAX_PARALLEL_CLIENTS", 4))
# Don't split tiny ranges across bots: every worker gets at least this many MB.
MIN_PARTS_PER_WORKER = max(1, _env_int("MIN_PARTS_PER_WORKER", 4))
# Hard cap on simultaneous open streams. Extra requests wait, then get 503.
MAX_CONCURRENT_STREAMS = max(1, _env_int("MAX_CONCURRENT_STREAMS", 4 if SLOW_CPU else _auto(12, 32, 100)))
# Per-IP cap, 0 = off. Keep it OFF behind Cloudflare/proxies: all users share the same IPs.
MAX_STREAMS_PER_IP = max(0, _env_int("MAX_STREAMS_PER_IP", 0))   # 0 = off
# How long an over-limit request waits for a free slot before a 503.
STREAM_QUEUE_TIMEOUT = max(1, _env_int("STREAM_QUEUE_TIMEOUT", 20))
# HARD global cap on 1 MB chunks buffered/in flight across ALL streams (= max RAM for
# streaming in MB). Every stream reserves its share first; if the pool is empty it waits.
MAX_INFLIGHT_CHUNKS = max(8, _env_int("MAX_INFLIGHT_CHUNKS", _auto(16, 48, 128)))
# A stream that gets no data from Telegram for this long is aborted (frees its slots).
STALL_TIMEOUT = max(10, _env_int("STALL_TIMEOUT", 45))
# One GetFile call: retries and per-attempt timeout (seconds).
FETCH_RETRIES = max(1, _env_int("FETCH_RETRIES", 5))
FETCH_TIMEOUT = max(5, _env_int("FETCH_TIMEOUT", 30))
# Max simultaneous GetFile calls PER BOT. Telegram answers FLOOD_WAIT when one bot is
# hammered; the limit auto-shrinks on a FloodWait and slowly grows back (min..max).
MAX_REQUESTS_PER_CLIENT = max(2, _env_int("MAX_REQUESTS_PER_CLIENT", 16))
MIN_REQUESTS_PER_CLIENT = max(1, _env_int("MIN_REQUESTS_PER_CLIENT", 3))
# Total seconds one chunk may spend waiting out FloodWaits before the stream gives up.
FLOOD_BUDGET = max(5, _env_int("FLOOD_BUDGET", 90))
# Longest FloodWait we are willing to sit out inside a stream (seconds).
MAX_FLOOD_SLEEP = max(1, _env_int("MAX_FLOOD_SLEEP", 20))
# Max bot clients (main + MULTI_TOKEN*); 0 = use ALL tokens you add. Every bot costs some RAM.
MAX_CLIENTS = max(0, _env_int("MAX_CLIENTS", 0))
# Above this share of the memory limit new streams are refused with 503 (instead of an OOM kill).
MEM_SHED_RATIO = max(0.5, min(0.98, _env_int("MEM_SHED_PERCENT", 85) / 100))
# Cache of link-expiry setting / file records to spare MongoDB (seconds).
SETTINGS_CACHE_TTL = max(1, _env_int("SETTINGS_CACHE_TTL", 30))
# Max cached file properties per bot client.
FILE_CACHE_SIZE = max(100, _env_int("FILE_CACHE_SIZE", 5000))


# 💾 __Disk cache__ (storage -> speed). Parts fetched from Telegram are kept in a sparse file, so a
# second user / a seek back / a resume is served from local disk at full speed and Telegram (and its
# FloodWait) is hit only once per part. Files bigger than the cache bypass it (direct streaming).
DISK_CACHE_DIR = environ.get("DISK_CACHE_DIR", "/tmp/filecache")


def _auto_cache_mb() -> int:
    import shutil
    try:
        free = shutil.disk_usage("/tmp").free / 1048576
    except Exception:
        return 0
    if SLOW_CPU:          # CPU is the scarce resource there; the cache would only add work
        return 0
    return int(min(free * 0.5, 4096)) if free >= 600 else 0


DISK_CACHE_MB = max(0, _env_int("DISK_CACHE_MB", _auto_cache_mb()))      # 0 = off
CACHE_READAHEAD = max(4, _env_int("CACHE_READAHEAD", 16))                # parts fetched ahead of the reader
CACHE_MAX_RUNS = max(1, _env_int("CACHE_MAX_RUNS", 3))                   # parallel fill jobs per file

# 🌐 __Web Server__
ON_HEROKU = 'DYNO' in environ
APP_NAME = environ.get('APP_NAME') if ON_HEROKU else None

PORT = _env_int('PORT', 8080)
NO_PORT = str(environ.get("NO_PORT", "true")).lower() in ("true", "1", "yes")
HAS_SSL = str(environ.get("HAS_SSL", "true")).lower() in ("true", "1", "yes")

# URL Generation
BIND_ADDRESS = environ.get("WEB_SERVER_BIND_ADDRESS", "")   ##without https:// paste the base url here 
FQDN = environ.get("FQDN", BIND_ADDRESS)

if not FQDN.startswith("http"):
    PROTOCOL = "https" if HAS_SSL else "http"
    PORT_SEGMENT = "" if NO_PORT else f":{PORT}"
    
    # Clean up trailing slashes for consistency
    FQDN = FQDN.rstrip('/')
    URL = f"{PROTOCOL}://{FQDN}{PORT_SEGMENT}/"
else:
    URL = FQDN

