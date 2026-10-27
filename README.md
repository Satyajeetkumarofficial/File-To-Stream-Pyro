# <div align="center">🚀 RexBots - Advanced File to Link Bot</div>

<div align="center">

<h3><b>A powerful Telegram bot that generates direct download and streaming links for any file.</b></h3>

Features a beautiful web interface, premium video player, and robust admin controls.

<a href="https://t.me/RexBots_Official">
  <img src="https://img.shields.io/badge/Join-Telegram%20Channel-blue.svg?style=for-the-badge&logo=telegram" alt="Join Telegram">
</a>
<a href="https://github.com/abhinai2244/FILE-TO-LINK-BOT.git">
  <img src="https://img.shields.io/badge/Repo-GitHub-black.svg?style=for-the-badge&logo=github" alt="GitHub Repo">
</a>

</div>

---

## 🌟 Key Features

### 📥 **File to Link Generation**
> - Generates **High-Speed Direct Download Links**.
> - Provides **Streaming Links** for video files.
> - Supports **all file types** (Video, Audio, Document, etc.).

### 📺 **Advanced Web Player**
> - **In-Browser Streaming**: Watch videos directly in the browser without downloading.
> - **External Player Support**: One-click integration with **MX Player**, **VLC**, and **PlayIt**.
> - **Responsive Design**: Beautiful, glassmorphism-themed UI compatible with Mobile & Desktop.
> - **Watermark Protection**: Custom persistent watermark on the player page.

### ⚡ **Batch Processing**
> - **Batch Link Creation**: Convert entire channels or multiple files into a single batch link.
> - **Post Protection**: Option to protect batch content from forwarding.

### 🔐 **Security & Verification**
> - **Token Verification**: Force users to verify via shortener links to access files.
> - **Force Subscribe**: Require users to join your channel before using the bot.
> - **Content Protection**: Prevent file forwarding (`protect_content` mode).

### 🛠️ **Admin Power**
> - **Broadcast**: Send messages to all bot users.
> - **User Management**: Ban/Unban users, view real-time statistics.
> - **Link Expiry**: Set auto-deletion timers for generated links using `/set_expiry`.
> - **Database**: Robust MongoDB integration for user data and file storage.

---

## 🤖 Bot Commands

### **Public Commands**
> - `/start` - Start the bot and get instructions.
> - `/help` - View help menu.
> - `/about` - View bot information.
> - `/files` - List your uploaded files.
> - `/del_files` - Manage and delete your files.

### **Admin Commands**
> - `/set_expiry [minutes]` - Set link expiry time (0 to disable).
> - `/ban_user [user_id] [reason]` - Ban a user.
> - `/unban_user [user_id]` - Unban a user.
> - `/broadcast` - Broadcast a message to all users.
> - `/stats` - View bot statistics.
> - `/batch` - Create a batch link for multiple files.

---

## 📋 Environment Variables

To run this bot, you need to set up the following environment variables:

- `API_ID`: Get this from **my.telegram.org**.
- `API_HASH`: Get this from **my.telegram.org**.
- `BOT_TOKEN`: Get this from **@BotFather**.
- `OWNER_ID`: Your Telegram User ID.
- `DATABASE_URI`: **MongoDB** connection string.
- `LOG_CHANNEL`: Channel ID for logs (start with -100).
- `FSUB`: (Optional) Feature Switch for Force Subscribe (True/False).

*(See `info.py` for the full list of configurable variables)*

---

## 🤝 Contributors

A huge thanks to the developers who made this project possible:

<div align="center">

| [**Abhi**](https://t.me/about_zani/143) | [**Abhinav**](https://t.me/adityaabhinav) | [**Master**](https://t.me/V_Sbotmaker) |
| :---: | :---: | :---: |
| Owner | Developer | Developer |

</div>

### 📡 Base Repository
Special thanks to [**Botsthe**](https://github.com/Botsthe/FILE-TO-LINK-BOT) for the original codebase.

---

## 📞 Support

For queries, feature requests, or bug reports, join our official channel:

<div align="center">
  <a href="https://t.me/RexBots_Official">
    <img src="https://img.shields.io/badge/RexBots-Official%20Channel-blue?style=for-the-badge&logo=telegram">
  </a>
</div>
