"""
All bot text constants — using HTML parse mode to avoid Markdown entity errors.
"""

TERMS_AND_CONDITIONS = """
📜 <b>TERMS &amp; CONDITIONS — BookFinderBot</b>

By using this bot, you agree to the following:

<b>1️⃣ Educational Use Only</b>
All books shared through this bot are intended strictly for personal, educational and research purposes only.

<b>2️⃣ Copyright Compliance</b>
Users must respect intellectual property rights of authors and publishers. Do <b>NOT</b> redistribute or sell any file received from this bot.

<b>3️⃣ No Misuse</b>
You must not use this bot for commercial purposes, piracy, or any activity that violates applicable laws in your jurisdiction.

<b>4️⃣ Availability</b>
Files are sourced from publicly available online libraries. The bot does not host any files itself.

<b>5️⃣ No Warranty</b>
The bot is provided "as is". We do not guarantee accuracy, completeness, or availability of any book.

<b>6️⃣ Auto-Deletion</b>
All bot messages are automatically deleted after 24 hours to conserve resources and protect privacy.

<b>7️⃣ Right to Modify</b>
These terms may be updated at any time without prior notice.

<b>8️⃣ Scam Policy</b>
Any attempt to scam, spam, or abuse the bot will result in an immediate and permanent ban.

<b>9️⃣ Takedown Policy</b>
If you are a rights holder and believe your content is being shared inappropriately, contact <b>@TechnicalSerena</b> immediately.

<b>🔟 Acceptance</b>
Continued use of this bot constitutes full acceptance of these terms.

<i>Last updated: 2025</i>
"""

PRIVACY_POLICY = """
🔐 <b>PRIVACY POLICY — BookFinderBot</b>

<b>📥 Data We Collect:</b>
• Telegram User ID (to process requests)
• Message content (only #request / #book queries)
• Timestamps (for auto-deletion scheduling)

<b>🚫 Data We Do NOT Collect:</b>
• Real name, phone number, or email
• Payment information
• Location data
• Browsing history

<b>⏳ Data Retention:</b>
All message data is automatically deleted after 24 hours. No long-term storage of personal data.

<b>🌐 Third-Party Services:</b>
This bot interacts with public libraries (LibGen, Open Library, Z-Library, etc.). Their own privacy policies apply independently.

<b>🔒 Security:</b>
No data is shared with any third party. The bot operates read-only on your Telegram messages.

<b>📩 Contact:</b>
For any privacy concerns: <b>@TechnicalSerena</b>
"""

DISCLAIMER = """
⚠️ <b>LEGAL DISCLAIMER — BookFinderBot</b>

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>📌 NATURE OF SERVICE</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

This bot is an <b>automated search and indexing tool</b> that links to books available on publicly accessible third-party websites and open digital libraries.

<u>We do NOT host, store, or distribute any copyrighted files.</u>
<u>We do NOT encourage, promote, or facilitate piracy.</u>

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>⚖️ APPLICABLE LAWS &amp; REGULATIONS</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

<b>🇺🇸 United States — DMCA (17 U.S.C. § 512)</b>
Under the Digital Millennium Copyright Act, this bot operates as a search intermediary. We respond promptly to all valid takedown notices.

<b>🇪🇺 European Union — DSA &amp; InfoSoc Directive</b>
Compliant with EU Directive 2001/29/EC on copyright and the Digital Services Act. User-generated requests are not our editorial content.

<b>🇮🇳 India — IT Act 2000 &amp; Copyright Act 1957</b>
Under Section 79 of the IT Act 2000, intermediaries are exempt from liability for third-party content provided they act in good faith. We comply fully with the Indian Copyright Act 1957.

<b>🌍 International — Berne Convention</b>
We acknowledge the Berne Convention for the Protection of Literary and Artistic Works and respect international copyright law.

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🛡️ SAFE HARBOR &amp; LIABILITY</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

• This bot functions as a <b>passive conduit</b> and search aggregator
• We do not have actual knowledge of infringing material
• Upon receiving valid notice, we will act <b>expeditiously</b> to remove or disable access
• Users are <b>solely responsible</b> for their own actions and the legality of their downloads in their jurisdiction
• Downloading copyrighted material without authorisation may be <b>illegal in your country</b>

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>📋 SOURCES USED</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

All results are sourced from:
• <b>LibGen</b> — publicly accessible research library
• <b>Project Gutenberg</b> — public domain works
• <b>Open Library / Internet Archive</b> — non-profit digital library
• <b>Z-Library</b> — open access library
• <b>Anna's Archive</b> — open-source shadow library index

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🚨 TAKEDOWN / DMCA NOTICE</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

If you are a <b>rights holder</b>, author, publisher, or authorised representative and believe your copyrighted work is being indexed inappropriately:

📩 Contact: <b>@TechnicalSerena</b> on Telegram

<u>Include in your notice:</u>
• Your full legal name and contact information
• Identification of the copyrighted work
• The specific content you wish removed
• A statement of good faith belief
• Your digital signature

<b>We will respond and act within 48 hours.</b>

<i>⚠️ This bot and its repository will be shut down and deleted immediately upon receiving a valid legal notice from any rights holder or organisation.</i>

<i>This repository is and will remain PRIVATE.</i>
"""

HELP_TEXT = """
📚 <b>BookFinderBot — Help Guide</b>

Hello! I help you find and download educational books from public libraries.

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🔍 HOW TO REQUEST A BOOK</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

Send a message in the group using <b>either</b>:

<code>#request &lt;book name or author&gt;</code>
<code>#book &lt;book name or author&gt;</code>

<b>Examples:</b>
• <code>#request Clean Code</code>
• <code>#book Atomic Habits</code>
• <code>#request Robert Martin</code>
• <code>#book python programming</code>
• <code>#request design patterns gang of four</code>

📌 Partial words supported! <code>#book clean co</code> will find <b>Clean Code</b>.

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>📥 HOW TO DOWNLOAD</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

After searching, the bot returns results like:

<code>📚 Clean Code
Robert C. Martin
🌐 English
/book_libgen_abc123 (pdf, 4.2 MB)</code>

Simply tap the <code>/book_...</code> command or the inline button to download!

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>⚙️ COMMANDS</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

/start — Welcome and help
/help — Show this guide
/terms — Terms and Conditions
/privacy — Privacy Policy
/sources — List of book sources

<b>━━━━━━━━━━━━━━━━━━━━━━</b>
<b>⚠️ NOTES</b>
<b>━━━━━━━━━━━━━━━━━━━━━━</b>

• Files above 100 MB are skipped automatically
• All messages auto-delete after 24 hours
• DM the bot? It will redirect you to the group
• Scammers will be banned immediately

💬 <b>Support:</b> @TechnicalSerena
"""

SOURCES_TEXT = """
📡 <b>Book Sources Used by This Bot</b>

1. 📗 <b>LibGen</b> (libgen.is) — Largest research library, primary source
2. 📘 <b>Project Gutenberg</b> (gutenberg.org) — 70,000+ free public domain classics
3. 📙 <b>Open Library</b> (openlibrary.org) — Internet Archive's digital library
4. 📕 <b>Z-Library</b> (z-library.bz / z-library.id) — Open access ebook library
5. 📓 <b>Anna's Archive</b> (annas-archive.org) — Meta-search across all libraries
6. 📔 <b>Internet Archive</b> (archive.org) — Non-profit digital preservation

<i>All sources are publicly accessible open libraries. No files are hosted by this bot.</i>
"""

START_TEXT = """
👋 <b>Welcome to BookFinderBot!</b>

I can search and deliver books from the world's largest open digital libraries — straight to Telegram!

📚 <b>What I can do:</b>
• Search millions of books across multiple sources
• Download PDFs, EPUBs, MOBIs and more
• Find by title, author, or partial keywords

👉 <b>To get started,</b> join our group and type:
<code>#request &lt;book name&gt;</code>
or
<code>#book &lt;book name&gt;</code>

Use /help for detailed instructions.
"""

DM_REDIRECT_TEXT = """
👋 Hey there!

I work in the <b>group</b>, not in DMs!

📌 Please join our group and use:
<code>#request &lt;book name&gt;</code>

👇 <b>Join here:</b>
"""

BOT_LOCKED_TEXT = "🔒 <b>Bot is currently locked.</b> Only owners can use it right now. Please try again later."

SCAM_WARNING = """
⚠️ <b>SCAM WARNING</b>

Please note:
• This bot is <b>FREE</b> — no one should ask you to pay for books.
• Never share your personal information, Telegram login, or payment details.
• Report scammers to @TechnicalSerena immediately.
"""

REACTIONS = [
    "👍", "❤️", "🔥", "🥰", "👏", "😁", "🤩", "🎉",
    "🤯", "😍", "🙏", "💯", "⚡", "🏆", "💎", "🚀",
    "📚", "✨", "💫", "🌟", "👀", "😎", "🤓", "🎊",
    "💪", "🥳", "😻", "🫡", "❤️‍🔥", "🫶"
]
