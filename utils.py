import asyncio
import logging
import aiohttp
import traceback
import random
import string
from datetime import datetime, timedelta, date, time
import pytz
from database.users_db import db
import info

# -------------------------- LOGGER INITIALIZATION -------------------------- #
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# -------------------------- TEMPORARY DATA STORAGE -------------------------- #
class Temp:
    ME = None
    BOT = None
    U_NAME = None
    B_NAME = None
    TOKENS = {}      # Temporary storage for user tokens
    VERIFIED = {}    # Cache for verified users

# -------------------------- PING SERVER -------------------------- #
async def ping_server():
    while True:
        await asyncio.sleep(info.PING_INTERVAL)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(info.URL) as resp:
                    logging.info(f"✅ Pinged server: {resp.status}")
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timeout: Could not ping server!")
        except Exception as e:
            logger.error(f"❌ Exception while pinging server: {e}")
            traceback.print_exc()

# -------------------------- LINK EXPIRY FORMATTER -------------------------- #
def format_link_expiry(seconds: int) -> str:
    """
    Convert link expiry seconds into human readable text
    """
    if not seconds or seconds <= 0:
        return "Never ❌"

    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    parts = []
    if days:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")

    return "⏳ " + ", ".join(parts)

# -------------------------- FILE SIZE CONVERTER -------------------------- #
def get_size(size: int) -> str:
    """Converts bytes to human-readable format."""
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"

# -------------------------- READABLE TIME FORMATTER -------------------------- #
def get_readable_time(seconds: int) -> str:
    """Converts seconds to a readable string (e.g., 1 days, 2h:30m:15s)."""
    result = ""
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f"{days} days "
    
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    seconds = int(seconds)
    
    result += f"{hours}:{minutes}:{seconds}"
    return result

# -------------------------- SHORT LINK GENERATOR -------------------------- #
async def get_short_link(link: str) -> str:
    """Generates a short link using the configured API."""
    api_key = info.SHORTLINK_API
    base_url = info.SHORTLINK_URL
    
    if not link.startswith("https"):
        link = link.replace("http", "https", 1)

    if base_url == "api.shareus.in":
        url = f"https://{base_url}/shortLink"
        params = {"token": api_key, "format": "json", "link": link}
    else:
        url = f"https://{base_url}/api"
        params = {"api": api_key, "url": link}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, ssl=False) as response:
                if response.status == 200:
                    data = await response.json(content_type="text/html" if base_url == "api.shareus.in" else None)
                    if data.get("status") == "success":
                        return data.get("shortlink") or data.get("shortenedUrl")
                    else:
                        logger.error(f"Shortener Error: {data.get('message', 'Unknown error')}")
                else:
                     logger.error(f"Shortener HTTP Error: {response.status}")
    except Exception as e:
        logger.error(f"Shortener Exception: {e}")

    # Fallback to manual construction if API fails
    return f"{url}?token={api_key}&link={link}"

async def get_verify_shorted_link(link):
    return await get_short_link(link)

async def get_shortlink(link):
    return await get_short_link(link)

# -------------------------- TOKEN HANDLING -------------------------- #
async def check_token(bot, userid, token):
    user = await bot.get_users(userid)
    tokens = Temp.TOKENS.get(user.id, {})
    return tokens.get(token) is False

async def get_token(bot, userid, link):
    user = await bot.get_users(userid)
    token = ''.join(random.choices(string.ascii_letters + string.digits, k=7))
    Temp.TOKENS[user.id] = {token: False}
    full_link = f"{link}verify-{user.id}-{token}"
    short_link = await get_verify_shorted_link(full_link)
    return short_link

# -------------------------- VERIFICATION STATUS -------------------------- #
async def get_verify_status(userid):
    status = Temp.VERIFIED.get(userid)
    if not status:
        status = await db.get_verified(userid)
        Temp.VERIFIED[userid] = status
    return status

async def update_verify_status(userid, date_temp, time_temp):
    status = await get_verify_status(userid)
    if status is None:
        status = {} 
    status["date"] = date_temp
    status["time"] = time_temp
    Temp.VERIFIED[userid] = status
    await db.update_verification(userid, date_temp, time_temp)

async def verify_user(bot, userid, token):
    user = await bot.get_users(int(userid))
    Temp.TOKENS[user.id] = {token: True}
    tz = pytz.timezone('Asia/Kolkata')
    expiry = datetime.now(tz) + timedelta(seconds=info.VERIFY_EXPIRE * 3600) # VERIFY_EXPIRE is in hours in info.py
    date_str = expiry.strftime("%Y-%m-%d")
    time_str = expiry.strftime("%H:%M:%S")
    await update_verify_status(user.id, date_str, time_str)

async def check_verification(bot, userid):
    user = await bot.get_users(int(userid))
    status = await get_verify_status(user.id)
    if not status:
        return False
        
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    
    try:
        exp_date = datetime.strptime(status["date"], "%Y-%m-%d").date()
        exp_time = datetime.strptime(status["time"], "%H:%M:%S").time()
        
        
        exp_datetime = tz.localize(datetime.combine(exp_date, exp_time))
        
        if now > exp_datetime:
             return False
    except Exception as e:
        logger.error(f"Invalid verification time format for user {userid}: {e}")
        return False
        
    return True
    
