"""
All bot text constants, messages, T&C, help text.
"""

TERMS_AND_CONDITIONS = """
📜 *TERMS & CONDITIONS — BookFinderBot*

By using this bot, you agree to the following:

1️⃣ *Educational Use Only*
   All books shared through this bot are intended for personal educational and research purposes only.

2️⃣ *Copyright Compliance*
   Users must respect the intellectual property rights of authors and publishers. Do NOT redistribute or sell any file received from this bot.

3️⃣ *No Misuse*
   You must not use this bot for commercial purposes, piracy, or any activity that violates applicable laws.

4️⃣ *Availability*
   Files are sourced from publicly available online libraries. The bot does not host any files itself.

5️⃣ *No Warranty*
   The bot is provided "as is". We do not guarantee the accuracy, completeness, or availability of any book.

6️⃣ *Auto-Deletion*
   All bot messages are automatically deleted after 24 hours to conserve resources and protect privacy.

7️⃣ *Right to Modify*
   These terms may be updated at any time without prior notice.

8️⃣ *Scam Policy*
   Any attempt to scam, spam, or abuse the bot will result in an immediate and permanent ban.

9️⃣ *Takedown Policy*
   If you are a rights holder and believe your content is being shared inappropriately, contact @Technical_serena immediately.

🔟 *Acceptance*
   Continued use of this bot constitutes acceptance of these terms.

_Last updated: 2025_
"""

PRIVACY_POLICY = """
🔐 *PRIVACY POLICY — BookFinderBot*

*Data We Collect:*
• Telegram User ID (to process requests)
• Message content (only #request queries)
• Timestamps (for auto-deletion scheduling)

*Data We Do NOT Collect:*
• Real name, phone number, or email
• Payment information
• Location data

*Data Retention:*
All message data is deleted after 24 hours automatically.

*Third-Party Services:*
This bot interacts with public libraries (Z-Library, Libgen, etc.). Their own privacy policies apply.

*Contact:*
For privacy concerns: @Technical_serena
"""

DISCLAIMER = """
⚠️ *DISCLAIMER*

This bot indexes and links to books available on *publicly accessible* websites and open libraries.

• We do NOT host any copyrighted files.
• We do NOT encourage piracy.
• All files are sourced from: Z-Library, Project Gutenberg, Open Library, Libgen, Anna's Archive, Internet Archive, and similar open-access repositories.

📩 *If you are a rights holder or an organisation and have concerns about this bot or its repository, please contact @Technical_serena on Telegram immediately. The bot will be shut down and the repository deleted without delay.*

_This repository is and will remain PRIVATE on GitHub._
"""

HELP_TEXT = """
📚 *BookFinderBot — Help Guide*

Hello! I help you find and download development & educational books from public libraries.

━━━━━━━━━━━━━━━━━━━━━━
🔍 *HOW TO REQUEST A BOOK*
━━━━━━━━━━━━━━━━━━━━━━

Send a message in the group with:

`#request <book name or author>`

*Examples:*
• `#request Clean Code`
• `#request Art of Being Alone`
• `#request Robert Martin`
• `#request python programming`
• `#request design patterns gang of four`

📌 Partial words are supported! `#request clean co` will still find *Clean Code*.

━━━━━━━━━━━━━━━━━━━━━━
📥 *HOW TO DOWNLOAD*
━━━━━━━━━━━━━━━━━━━━━━

After searching, the bot returns results like:

```
📚 Clean Code
Robert C. Martin
🌐 English
/book_aXyZ123 (pdf, 4.2 MB)
```

Simply tap the `/book_...` command or the inline button to download!

━━━━━━━━━━━━━━━━━━━━━━
⚙️ *COMMANDS*
━━━━━━━━━━━━━━━━━━━━━━

/start — Welcome & help
/help — Show this guide
/terms — Terms & Conditions
/privacy — Privacy Policy
/sources — List of book sources

━━━━━━━━━━━━━━━━━━━━━━
👑 *OWNER-ONLY COMMANDS*
━━━━━━━━━━━━━━━━━━━━━━

/lock — Lock bot (disable for all users)
/unlock — Unlock bot
/broadcast <message> — Send message to all users
/restart — Restart the bot

━━━━━━━━━━━━━━━━━━━━━━
⚠️ *NOTES*
━━━━━━━━━━━━━━━━━━━━━━

• Files above 100 MB are skipped automatically
• All messages auto-delete after 24 hours
• DM the bot? It'll redirect you to the group!
• Scammers will be banned immediately

💬 *Support:* @Technical_serena
"""

SOURCES_TEXT = """
📡 *Book Sources Used by This Bot*

1. 📗 [Z-Library](https://z-lib.id) — Largest book library
2. 📘 [Project Gutenberg](https://gutenberg.org) — 70,000+ free classics
3. 📙 [Open Library](https://openlibrary.org) — Internet Archive's library
4. 📕 [Libgen](https://libgen.li) — Scientific articles & books
5. 📓 [Anna's Archive](https://annas-archive.org) — Meta-search across all libraries
6. 📔 [Internet Archive](https://archive.org) — Digital preservation
7. 📒 [PDF Drive](https://pdfdrive.webs.nf) — PDF search engine
8. 📃 [PDF Books World](https://pdfbooksworld.com) — Free PDF books

_All sources are publicly accessible open libraries._
"""

START_TEXT = """
👋 *Welcome to BookFinderBot!*

I can search and deliver books from the world's largest open digital libraries — straight to your Telegram!

📚 *What I can do:*
• Search millions of books
• Download PDFs, EPUBs, MOBIs
• Find by title, author, or partial keywords

👉 *To get started,* join our group and type:
`#request <book name>`

Use /help for detailed instructions.
"""

DM_REDIRECT_TEXT = """
👋 Hey there!

I work in the *group*, not in DMs!

📌 Please join our group and use:
`#request <book name>`

👇 *Join here:*
"""

BOT_LOCKED_TEXT = "🔒 *Bot is currently locked.* Only owners can use it right now. Please try again later."

SCAM_WARNING = """
⚠️ *SCAM WARNING*

Please note:
• This bot is *FREE* — no one should ask you to pay for books.
• Never share your personal information, Telegram login, or payment details.
• Report scammers to @Technical_serena immediately.
"""

REACTIONS = [
    "👍", "❤️", "🔥", "🥰", "👏", "😁", "🤩", "🎉",
    "🤯", "😍", "🙏", "💯", "⚡", "🏆", "💎", "🚀",
    "📚", "✨", "💫", "🌟", "👀", "😎", "🤓", "🎊",
    "💪", "🥳", "😻", "🫡", "❤️‍🔥", "🫶"
]
