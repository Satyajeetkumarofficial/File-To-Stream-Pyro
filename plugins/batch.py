import os
import re
import json
import base64
from struct import pack
from pyrogram import Client, filters
from pyrogram.types import Message

from pyrogram.errors import ChannelInvalid, UsernameInvalid, UsernameNotModified
from pyrogram.file_id import FileId
from info import LOG_CHANNEL, ADMINS, PUBLIC_FILE_STORE, BOT_USERNAME

async def allowed(_, __, message):
    if PUBLIC_FILE_STORE:
        return True
    if message.from_user and message.from_user.id in ADMINS:
        return True
    return False
    
# ✅ FileId Encoding Helpers
def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(new_file_id: str):
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref


# ✅ BATCH HANDLER
@Client.on_message(filters.command(['batch']) & filters.create(allowed))
async def gen_link_batch(bot, message: Message):
    if " " not in message.text:
        return await message.reply("Use correct format.\nExample <code>/batch https://t.me/ProBotUpdate/30 https://t.me/ProBotUpdate/40</code>.")

    links = message.text.strip().split(" ")
    if len(links) != 3:
        return await message.reply("Use correct format.\nExample <code>/batch https://t.me/ProBotUpdate/15 https://t.me/ProBotUpdate/22</code>.")

    cmd, first, last = links
    regex = re.compile(r"(https://)?(t\.me|telegram\.me|telegram\.dog)/(c/)?([\d\w_]+)/(\d+)")
    
    match = regex.match(first)
    if not match:
        return await message.reply("Invalid link")
    
    f_chat_id = match.group(4)
    f_msg_id = int(match.group(5))
    if f_chat_id.isnumeric():
        f_chat_id = int("-100" + f_chat_id)

    match = regex.match(last)
    if not match:
        return await message.reply("Invalid link")
    
    l_chat_id = match.group(4)
    l_msg_id = int(match.group(5))
    if l_chat_id.isnumeric():
        l_chat_id = int("-100" + l_chat_id)

    if f_chat_id != l_chat_id:
        return await message.reply("Chat ids not matched.")

    try:
        chat_id = (await bot.get_chat(f_chat_id)).id
    except ChannelInvalid:
        return await message.reply("This may be a private channel / group. Make me an admin there.")
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply("Invalid Link specified.")
    except Exception as e:
        return await message.reply(f"Errors - {e}")

    sts = await message.reply("Generating link for your message. This may take time...")

    # ✅ Begin media extraction
    FRMT = "Generating Link...\nTotal Messages: `{total}`\nDone: `{current}`\nRemaining: `{rem}`\nStatus: `{sts}`"
    outlist = []
    og_msg = 0
    tot = 0

    async for msg in bot.iter_messages(f_chat_id, l_msg_id, f_msg_id):
        tot += 1
        if msg.empty or msg.service or not msg.media:
            continue
        try:
            file_type = msg.media
            file = getattr(msg, file_type.value)
            caption = getattr(msg, 'caption', '')
            if caption:
                caption = caption.html
            if file:
                outlist.append({
                    "file_id": file.file_id,
                    "caption": caption,
                    "title": getattr(file, "file_name", ""),
                    "size": file.file_size,
                    "protect": cmd.lower().strip() == "/pbatch",
                })
                og_msg += 1
        except Exception:
            pass
        if not og_msg % 20:
            try:
                await sts.edit(FRMT.format(total=l_msg_id - f_msg_id, current=tot, rem=(l_msg_id - f_msg_id - tot), sts="Saving..."))
            except:
                pass

    filename = f"batchmode_{message.from_user.id}.json"
    with open(filename, "w") as out:
        json.dump(outlist, out)

    post = await bot.send_document(LOG_CHANNEL, filename, file_name="Batch.json", caption="⚠️Generated for filestore.")
    os.remove(filename)

    file_id, ref = unpack_new_file_id(post.document.file_id)
    await sts.edit(f"Here is your link\nContains `{og_msg}` files.\nhttps://t.me/{BOT_USERNAME}?start=BATCH-{file_id}")
