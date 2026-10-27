class script(object):
    START_TXT = """<b>👋 Hey {},</b>\n\n🤖 I’m <b>{}</b> 🚀 — just send me any <b>file or video</b> 📤 and I’ll instantly convert it into 🔗 <b>direct download</b> & 🎬 <b>smooth streaming links</b> ⚡ with fast processing and reliable access.\n\n➕ You can also add me as an <b>admin</b> to your channel 📢 and I’ll automatically create download & stream links with ready-to-use buttons for every media you post ✨ making sharing easy and seamless.\n\n📢 <a href="https://t.me/ProBotXUpdate">➜ Join Update Channel</a>"""
    
    RESTART_TXT = """\n<b>Bᴏᴛ Rᴇsᴛᴀʀᴛᴇᴅ !\n\n📅 Dᴀᴛᴇ : <code>{}</code>\n⏰ Tɪᴍᴇ : <code>{}</code>\n🌐 Tɪᴍᴇᴢᴏɴᴇ : <code>Asia/Kolkata</code>\n🛠️ Bᴜɪʟᴅ Sᴛᴀᴛᴜs: <code>v4.6.00 [ Sᴛᴀʙʟᴇ ]</code></b>"""

    HELP_TXT = """<blockquote><b>You don't need many commands to use this bot\n\nJust send me files and I will give you direct download & streaming link\n\nAlso you can use me in your channel just add me and make me admin and see my power 💥\n\nFor more, use /help command\nMore, use /about command</b></blockquote>"""
    
    ADMIN_CMD_TXT = """<blockquote><b>\n\n# Admin Only Commands 👑  \n/ban - Ban a user/channel [FOR ADMINS USE ONLY]  \n/unban - Unban a user/channel [FOR ADMINS USE ONLY]  \n/broadcast - Send broadcast message [FOR ADMINS USE ONLY]  \n/pin_broadcast - Pin broadcast message [FOR ADMINS USE ONLY]  \n/restart - Restart the bot [FOR ADMINS USE ONLY]  \n/stats - Show bot statistics [FOR ADMINS USE ONLY]  \n/blocked - List of blocked users [FOR ADMINS USE ONLY] \n</b></blockquote>"""

    HELP2_TXT = """<blockquote><b>How to Use File to Link Bot\n\nBasic Usage:\n• Send any file or media from Telegram\n• Bot will generate permanent download and stream links\n• Use these links to download or stream content through our servers\n• For streaming, paste the provided link in any video player\n\nKey Features:\n• Permanent link generation\n• Direct download support\n• Video streaming capability\n• Channel support (Add bot as admin)\n• Custom shortener integration\n• Unlimited file size support\n\nChannel Usage:\n1. Add bot as admin to your channel\n2. Bot will automatically process files\n3. Links will be generated for all media\n\n⚠️ Important Notes:\n• All links are permanent and won't expire\n• Sharing inappropriate content will result in permanent ban\n• Report any issues to our support team\n\n🔞 Adult content strictly prohibited.\n\n📮 Help & Support:\n• Updates: @ProBotUpdate\n• Support: @ProBotUpdate\n\n <u><i>Report bugs to <a href='https://t.me/Satyajeetkumarofficial'>Developer</a></u></i></b></blockquote>"""

    CAPTION = """🎬 <i><a href='{}'>{}</a></i>"""
    
    LOG_TEXT = """<b>#NewUser {}\n    \nID - <code>{}</code>\nNᴀᴍᴇ - {}</b>"""

    ABOUT_TXT = """<blockquote><b>╔══❰ {} ❱═════❍\n║╭━━━━━━━━━━━━━━━━━━➣\n║┣⪼🤖My Name : {}\n║┣⪼👦Developer : <a href='https://t.me/Satyajeetkumarofficial'>Owner</a>\n║┣⪼❣️Update : <a href=https://t.me/ProBotUpdate>Pro Botz</a>\n║┣⪼⏲️Bot Uptime :- {}\n║┣⪼📡Hosted On : Koyeb \n║┣⪼🗣️Language : Python \n║┣⪼📚Library : Pyrogram\n║┣⪼🗒️Version : {} [Stable]\n║╰━━━━━━━━━━━━━━━➣\n╚══════════════════❍ </b></blockquote>"""

    AUTH_TXT = """<i><b>Hᴇʏ {}! 👋\n\nTᴏ ᴄᴏɴᴛɪɴᴜᴇ ᴜsɪɴɢ ᴛʜɪs ʙᴏᴛ, ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴏᴜʀ ᴜᴘᴅᴀᴛᴇs ᴄʜᴀɴɴᴇʟ 💬\n\nSᴇʀᴠᴇʀ ʟᴏᴀᴅ ɪs ʜɪɡʜ, sᴏ ᴀᴄᴄᴇss ɪs ʟɪᴍɪᴛᴇᴅ ᴛᴏ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ ᴍᴇᴍʙᴇʀs ᴏɴʟʏ 🚀</b></i>"""

    CAPTION_TXT = """\n<i><u>Your Link Generated !</u></i>\n\n<blockquote><b>📧 File Name :- </b> <i><a href={}>{}</a></i>\n\n<b>📦 File Size :- </b> <i>{}</i>\n\n<b><u><i>Tap To Copy Link 👇</i></u></b>\n\n<b>🖥 Stream  : </b> <code>{}</code>\n\n<b>📥 Download : </b> <code>{}</code>\n\n<b>⏳ Link Expiry :- </b> <i>{}</i>\n\n<b>🚸 Any issues dm : https://t.me/ProBotUpdate</b></blockquote>"""

    VERIFICATION_TEXT = """<b>👋 ʜᴇʏ {},\n\n📌 <u>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴠᴇʀɪꜰɪᴇᴅ ᴛᴏᴅᴀʏ, ᴛᴀᴘ ᴏɴ ᴛʜᴇ ᴠᴇʀɪꜰʏ ʟɪɴᴋ & ɢᴇᴛ ᴜɴʟɪᴍɪᴛᴇᴅ ᴀᴄᴄᴇss ꜰᴏʀ ɴᴇxᴛ ꜰᴜʟʟ ᴅᴀʏ.</u></b>"""
    
    VERIFIED_COMPLETE_TEXT = """<b>👋 ʜᴇʏ {},\n\nʏᴏᴜ ᴀʀᴇ ɴᴏᴡ ᴠᴇʀɪꜰɪᴇᴅ ꜰᴏʀ ᴛᴏᴅᴀʏ ☺️.\nᴇɴᴊᴏʏ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏᴠɪᴇs ᴏʀ sᴇʀɪᴇs ʟɪɴᴋs 💥.</b>"""
    
    VERIFIED_LOG_TEXT = """<b><u>☄ ᴜsᴇʀ ᴠᴇʀɪꜰɪᴇᴅ sᴜᴄᴄᴇssꜰᴜʟʟʏ ☄</u>\n\n⚡️ ɴᴀᴍᴇ:- {} [ <code>{}</code> ] \n📆 ᴅᴀᴛᴇ:- <code>{} </code></b>\n\n#verified_completed"""

