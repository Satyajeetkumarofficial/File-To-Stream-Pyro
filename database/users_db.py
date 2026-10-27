from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from info import DB_URL, DB_NAME 
import time, pytz

client = AsyncIOMotorClient(DB_URL)
mydb = client[DB_NAME]
    
class Database:
    def __init__(self):
        self.users = mydb.users
        self.blocked_users = mydb.blocked_users
        self.blocked_channels = mydb.blocked_channels
        self.files = mydb.files
        
    # 🧑‍💻 USER SYSTEM ------------------------------

    def new_user(self, id, name):
        return {
            "id": id,
            "name": name,
            "verification_status": {
                "date": "1999-12-31",
                "time": "23:59:59"
            }
        }

    async def add_user(self, id, name):
        if not await self.is_user_exist(id):
            user = self.new_user(id, name)
            await self.users.insert_one(user)

    async def is_user_exist(self, id):
        return bool(await self.users.find_one({'id': int(id)}))

    async def total_users_count(self):
        return await self.users.count_documents({})

    async def get_all_users(self):
        return self.users.find({})

    async def delete_user(self, user_id):
        await self.users.delete_many({'id': int(user_id)})
        
    # ✅ VERIFICATION SYSTEM -----------------------

    async def update_verification(self, id, date, time):
        status = {
            'date': str(date),
            'time': str(time)
        }
        await self.users.update_one(
            {'id': int(id)},
            {'$set': {'verification_status': status}}
        )

    async def get_verified(self, id):
        default = {
            'date': "1999-12-31",
            'time': "23:59:59"
        }
        user = await self.users.find_one({'id': int(id)})
        if user:
            return user.get("verification_status", default)
        return default
        
    async def get_all_verified_users(self):
        cursor = self.users.find({
            "verification_status.date": {"$ne": "1999-12-31"}
        })
        verified_users = []
        async for user in cursor:
            verified_users.append(user)
        return verified_users

    async def get_verified_users_count(self):
        return await self.users.count_documents({"verification_status.status": "verified"})
    
    # 🚫 USER BAN SYSTEM ---------------------------

    async def is_user_blocked(self, user_id: int) -> bool:
        return await self.blocked_users.find_one({"user_id": user_id}) is not None

    async def get_block_data(self, user_id: int):
        return await self.blocked_users.find_one({"user_id": user_id})

    async def block_user(self, user_id: int, reason: str = "No reason provided."):
        await self.blocked_users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "reason": reason,
                    "blocked_at": datetime.utcnow()
                }
            },
            upsert=True
        )

    async def unblock_user(self, user_id: int):
        await self.blocked_users.delete_one({"user_id": user_id})

    async def get_all_blocked_users(self):
        return self.blocked_users.find({})

    async def total_blocked_count(self):
        return await self.blocked_users.count_documents({})

    # 📣 CHANNEL BAN SYSTEM ------------------------

    async def is_channel_blocked(self, channel_id: int) -> bool:
        return await self.blocked_channels.find_one({"channel_id": channel_id}) is not None

    async def block_channel(self, channel_id: int, reason: str = "No reason provided."):
        await self.blocked_channels.update_one(
            {"channel_id": channel_id},
            {
                "$set": {
                    "channel_id": channel_id,
                    "reason": reason,
                    "blocked_at": datetime.utcnow()
                }
            },
            upsert=True
        )

    async def unblock_channel(self, channel_id: int):
        await self.blocked_channels.delete_one({"channel_id": channel_id})

    async def get_all_blocked_channels(self):
        return self.blocked_channels.find({})

    async def get_channel_block_data(self, channel_id: int):
        return await self.blocked_channels.find_one({"channel_id": channel_id})

    async def total_blocked_channels_count(self):
        return await self.blocked_channels.count_documents({})

    async def get_user(self, user_id):
        user_data = await self.users.find_one({"id": user_id})
        return user_data
        
    async def update_user(self, user_data):
        await self.users.update_one({"id": user_data["id"]}, {"$set": user_data}, upsert=True)

    async def has_premium_access(self, user_id):
        user_data = await self.get_user(user_id)
        if user_data:
            expiry_time = user_data.get("expiry_time")
            if expiry_time is None:
                return False
            elif isinstance(expiry_time, datetime) and datetime.now() <= expiry_time:
                return True
            else:
                await self.users.update_one({"id": user_id}, {"$set": {"expiry_time": None}})
        return False
        
    async def update_one(self, filter_query, update_data):
        try:
            result = await self.users.update_one(filter_query, update_data)
            return result.matched_count == 1
        except Exception as e:
            print(f"Error updating document: {e}")
            return False
            
    async def all_premium_users_count(self):
        count = await self.users.count_documents({
        "expiry_time": {"$gt": datetime.now()}
        })
        return count

    async def get_expired(self, current_time):
        expired_users = []
        cursor = self.users.find({"expiry_time": {"$lt": current_time}})
        async for user in cursor:
            expired_users.append(user)
        return expired_users

# Inside your DB manager class
    async def get_expiring_soon(self, label, delta):
        reminder_key = f"reminder_{label}_sent"
        now = datetime.utcnow()
        target_time = now + delta
        window = timedelta(seconds=30)

        start_range = target_time - window
        end_range = target_time + window

        reminder_users = []
        cursor = self.users.find({
            "expiry_time": {"$gte": start_range, "$lte": end_range},
            reminder_key: {"$ne": True}
        })

        async for user in cursor:
            reminder_users.append(user)
            await self.users.update_one(
                {"id": user["id"]}, {"$set": {reminder_key: True}}
            )

        return reminder_users

    async def remove_premium_access(self, user_id):
        return await self.update_one(
            {"id": user_id}, {"$set": {"expiry_time": None}}
        )

    # ⚙️ SETTINGS SYSTEM ---------------------------
    async def get_link_expiry(self):
        # Default to 0 (No Expiry) if not set
        setting = await mydb.settings.find_one({"name": "link_expiry"})
        return setting["value"] if setting else 0

    async def set_link_expiry(self, seconds: int):
        await mydb.settings.update_one(
            {"name": "link_expiry"},
            {"$set": {"value": seconds}},
            upsert=True
        )

db = Database()
