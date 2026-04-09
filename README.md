# 📚 BookFinderBot

<div align="center">

![BookFinderBot Banner](https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=200&section=header&text=BookFinderBot&fontSize=60&fontColor=fff&animation=twinkling&fontAlignY=35&desc=Telegram+Book+Finder+%26+Downloader+Bot&descAlignY=55&descSize=18)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21.5-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://github.com/python-telegram-bot/python-telegram-bot)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com)
[![License](https://img.shields.io/badge/Repo-Private-red?style=for-the-badge&logo=github)](https://github.com)

![Maintained](https://img.shields.io/badge/Maintained-Yes-green?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)
![Sources](https://img.shields.io/badge/Book%20Sources-8+-orange?style=flat-square)

> 🤖 A powerful Telegram bot that searches and downloads books from 8+ public libraries — PDFs, EPUBs, MOBIs and more!

</div>

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Multi-Source Search** | Searches Z-Library, Libgen, Anna's Archive, Gutenberg, Open Library & more simultaneously |
| 📥 **Auto Download** | Downloads and sends the actual file directly in Telegram |
| 📊 **Live Progress** | Real-time download progress with speed, ETA, and % bar |
| 🎉 **Reactions** | Bot reacts with random animated emojis to every user message |
| 🔒 **Lock/Unlock** | Owners can lock/unlock the bot instantly |
| 📢 **Broadcast** | Send messages to all bot users at once |
| ⏰ **Auto-Delete** | All bot messages auto-delete after 24 hours |
| 🚫 **Size Filter** | Skips files above 100 MB to save bandwidth |
| 🐳 **Docker Ready** | Full Docker + docker-compose setup |
| ☁️ **Render Deploy** | One-click deploy on Render free tier |
| 🔐 **Privacy Policy** | Built-in T&C, Privacy Policy, Disclaimer |
| 🤝 **Scam Protection** | Redirects DMs, warns about scams |

---

## 📡 Book Sources

| Source | URL | Type |
|---|---|---|
| 📗 Z-Library | [z-lib.id](https://z-lib.id) | Login supported |
| 📘 Libgen | [libgen.li](https://libgen.li) / [libgen.im](https://libgen.im) | Free |
| 📙 Anna's Archive | [annas-archive.org](https://annas-archive.org) | Meta-search |
| 📕 Project Gutenberg | [gutenberg.org](https://gutenberg.org) | Public domain |
| 📓 Open Library | [openlibrary.org](https://openlibrary.org) | Free |
| 📔 Internet Archive | [archive.org](https://archive.org) | Free |
| 📒 PDF Drive | [pdfdrive.webs.nf](https://pdfdrive.webs.nf) | Free |
| 📃 PDF Books World | [pdfbooksworld.com](https://pdfbooksworld.com) | Free |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- A Telegram Group/Channel ID

### 1. Clone & Setup

```bash
git clone https://github.com/yourusername/bookfinderbot.git
cd bookfinderbot
cp .env.example .env
# Edit .env with your values
```

### 2. Run with Docker (Recommended)

```bash
docker compose up -d
```

### 3. Run Locally

```bash
pip install -r requirements.txt
python main.py
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```env
BOT_TOKEN=your_bot_token_here
REQUEST_GROUP_ID=-1001234567890
REQUEST_GROUP_LINK=https://t.me/your_group
ZLIB_EMAIL=your_email@gmail.com
ZLIB_PASSWORD=your_password
START_IMAGE_URL=https://telegra.ph/file/your-image.jpg
```

All config options are in `.env.example` with comments.

---

## ☁️ Deploy on Render (Free)

1. Push this repo to **GitHub** (keep it **Private**)
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Render auto-detects `render.yaml`
5. Add your **environment variables** in Render dashboard
6. Click **Deploy**!

> ⚠️ Set `USE_WEBHOOK=true` and `WEBHOOK_URL=https://yourapp.onrender.com` on Render.

---

## 🤖 Bot Commands

### Public Commands
| Command | Description |
|---|---|
| `/start` | Welcome message with image |
| `/help` | Detailed usage guide |
| `/terms` | Terms & Conditions |
| `/privacy` | Privacy Policy |
| `/sources` | List of book sources |
| `/disclaimer` | Copyright disclaimer |

### Owner-Only Commands
| Command | Description |
|---|---|
| `/lock` | Lock bot for all users |
| `/unlock` | Unlock bot |
| `/broadcast <msg>` | Message all users |
| `/restart` | Restart the bot |

---

## 📖 How to Use

### In the Group:

```
#request Clean Code
#request Art of Being Alone
#request Robert Martin
#request python programming
#request design patterns gang of four
```

> Partial words work! `#request clean co` finds *Clean Code*

### Results look like:

```
📚 Clean Code
✍️ Robert C. Martin
🌐 English  📄 PDF  📦 4.2 MB
/book_zlib_12345  (Z-Library)

📚 Clean Code: A Handbook
✍️ Robert Martin
🌐 English  📗 EPUB  📦 1.1 MB
/book_libgen_abc123  (Libgen)
```

### Then tap `/book_...` or the inline button to download!

---

## 🏗️ Project Structure

```
bookfinderbot/
├── main.py                    # Entry point
├── config.py                  # All configuration
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── render.yaml
├── .env.example
├── .gitignore
└── src/
    ├── constants.py           # All bot text, T&C, help
    ├── database.py            # JSON storage, auto-delete
    ├── scheduler.py           # Background jobs
    ├── handlers/
    │   ├── commands.py        # /start, /help, /lock etc.
    │   └── book_request.py    # #request, /book_, DM handling
    └── sources/
        ├── __init__.py        # Aggregator
        ├── zlibrary_source.py
        ├── libgen_source.py
        ├── annas_source.py
        ├── gutenberg_source.py
        └── openlibrary_source.py
```

---

## ⚠️ Disclaimer

This bot searches and links to books available on **publicly accessible** websites and open digital libraries.

- ❌ We do **NOT** host any copyrighted files
- ❌ We do **NOT** encourage piracy
- ✅ All files sourced from open-access repositories only
- ✅ For **personal educational use only**

---

## 📩 Takedown / Contact

> **If you are a rights holder or an organisation and have concerns about this bot or its repository, please contact [@Technical_serena](https://t.me/Technical_serena) on Telegram immediately.**
>
> The bot will be shut down and the repository deleted without delay.

**This repository is and will always remain PRIVATE on GitHub.**

---

<div align="center">

![Footer](https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=100&section=footer)

Made with ❤️ | Contact: [@Technical_serena](https://t.me/Technical_serena)

</div>
