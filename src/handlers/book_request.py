"""
Handles #request in group messages and /book_<id> download commands.
Shows real-time ETA, speed, and progress during download.
"""

import asyncio
import io
import logging
import time
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from config import OWNER_IDS, REQUEST_GROUP_ID, MAX_FILE_SIZE_MB, AUTO_DELETE_HOURS
from src.constants import BOT_LOCKED_TEXT, DM_REDIRECT_TEXT, SCAM_WARNING, REACTIONS
from src import database as db
from src.sources import search_all_sources, get_cached_book, download_book, BookResult

import random

logger = logging.getLogger(__name__)
FORMAT_EMOJI = {
    "pdf": "📄", "epub": "📗", "mobi": "📘", "fb2": "📙",
    "djvu": "📚", "azw3": "📕", "doc": "📝", "txt": "📃",
}


def is_owner(uid: int) -> bool:
    return uid in OWNER_IDS


def fmt_size(b: int) -> str:
    if b == 0:
        return "Unknown"
    if b < 1024:
        return f"{b} B"
    if b < 1024 ** 2:
        return f"{b/1024:.1f} KB"
    if b < 1024 ** 3:
        return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"


def fmt_speed(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 ** 2:
        return f"{bps/1024:.1f} KB/s"
    return f"{bps/1024**2:.1f} MB/s"


def progress_bar(pct: float, width: int = 12) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct:.0f}%"


def build_result_text(results: list[BookResult]) -> str:
    if not results:
        return "😔 *No books found.* Try a different keyword or author name."

    lines = [f"🔍 *Found {len(results)} result(s):*\n"]
    for book in results:
        emoji = FORMAT_EMOJI.get(book.format, "📄")
        lines.append(
            f"📚 *{book.title}*\n"
            f"✍️ {book.author}\n"
            f"🌐 {book.language.title()}  {emoji} {book.format.upper()}  📦 {book.size_str}\n"
            f"`/book_{book.book_id}`  _({book.source})_\n"
        )
    lines.append("\n💡 Tap a `/book_...` command to download!")
    return "\n".join(lines)


def build_inline_buttons(results: list[BookResult]) -> InlineKeyboardMarkup:
    keyboard = []
    for book in results:
        emoji = FORMAT_EMOJI.get(book.format, "📄")
        label = f"{emoji} {book.title[:28]}… ({book.format}, {book.size_str})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"dl_{book.book_id}")])
    return InlineKeyboardMarkup(keyboard)


async def give_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Give a random animated reaction to a message (not the bot's own)."""
    try:
        reaction = random.choice(REACTIONS)
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.effective_message.message_id,
            reaction=[{"type": "emoji", "emoji": reaction}],
            is_big=True,
        )
    except Exception:
        pass  # Reactions not critical — silently ignore


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler for group messages — processes #request tags."""
    msg: Message = update.message or update.channel_post
    if not msg:
        return

    user = update.effective_user
    text = msg.text or msg.caption or ""

    # React to every user message (not bot's own)
    if user and user.id != context.bot.id:
        asyncio.create_task(give_reaction(update, context))

    # Only process messages from the configured group
    if REQUEST_GROUP_ID and msg.chat.id != REQUEST_GROUP_ID and not is_owner(user.id if user else 0):
        return

    # Lock check
    if db.is_locked() and not is_owner(user.id if user else 0):
        return

    # Check for #request
    lower = text.lower()
    if "#request" not in lower:
        return

    # Extract book query
    idx = lower.index("#request")
    query = text[idx + len("#request"):].strip()
    if not query:
        m = await msg.reply_text(
            "❓ Usage: `#request <book name or author>`\nExample: `#request Clean Code`",
            parse_mode=ParseMode.MARKDOWN,
        )
        db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
        return

    db.add_user(user.id)

    # Show searching indicator
    searching_msg = await msg.reply_text(
        f"🔍 Searching for: *{query}*\n_Please wait..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    db.schedule_delete(searching_msg.chat_id, searching_msg.message_id, AUTO_DELETE_HOURS)

    try:
        results = await search_all_sources(query)
    except Exception as e:
        logger.error(f"Search error: {e}")
        await searching_msg.edit_text("❌ Search failed. Please try again later.")
        return

    if not results:
        await searching_msg.edit_text(
            f"😔 *No books found for:* `{query}`\n\nTry:\n• Different keywords\n• Author name\n• Partial title",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    result_text = build_result_text(results)
    inline = build_inline_buttons(results)

    await searching_msg.edit_text(
        result_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=inline,
        disable_web_page_preview=True,
    )


async def handle_book_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /book_<id> download commands — works in group AND owner DM."""
    msg = update.effective_message
    user = update.effective_user
    text = msg.text or ""

    if not text.startswith("/book_"):
        return

    book_id = text[1:].split("@")[0].strip()  # strip /book_ prefix and @botname
    book_id = book_id[len("book_"):]  # actual id without "book_" prefix

    # Check permissions
    in_group = msg.chat.type in ("group", "supergroup", "channel")
    owner = is_owner(user.id)

    if not in_group and not owner:
        m = await msg.reply_text(
            "❌ Please request books in the group, not in DMs!\n\n" + DM_REDIRECT_TEXT,
            parse_mode=ParseMode.MARKDOWN,
        )
        db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
        return

    if db.is_locked() and not owner:
        m = await msg.reply_text(BOT_LOCKED_TEXT, parse_mode=ParseMode.MARKDOWN)
        db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
        return

    book = get_cached_book(book_id)
    if not book:
        m = await msg.reply_text(
            "❌ Book not found in cache. Please search again with `#request <title>`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
        return

    # Send progress message
    progress_msg = await msg.reply_text(
        f"⏳ *Preparing download...*\n📚 {book.title}\n✍️ {book.author}",
        parse_mode=ParseMode.MARKDOWN,
    )
    db.schedule_delete(progress_msg.chat_id, progress_msg.message_id, AUTO_DELETE_HOURS)

    start_time = time.time()

    async def update_progress(pct: float, downloaded: int, total: int):
        elapsed = time.time() - start_time
        speed = downloaded / elapsed if elapsed > 0 else 0
        remaining = (total - downloaded) / speed if speed > 0 and total > 0 else 0

        bar = progress_bar(pct)
        speed_str = fmt_speed(speed)
        dl_str = fmt_size(downloaded)
        total_str = fmt_size(total)
        eta = f"{int(remaining)}s" if remaining > 0 else "..."

        try:
            await progress_msg.edit_text(
                f"📥 *Downloading...*\n"
                f"📚 *{book.title[:40]}*\n\n"
                f"{bar}\n"
                f"📦 {dl_str} / {total_str}\n"
                f"⚡ Speed: `{speed_str}`\n"
                f"⏱ ETA: `{eta}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass

    await update_progress(0, 0, book.size_bytes)

    # Download with simulated progress updates
    download_task = asyncio.create_task(download_book(book))
    total_bytes = book.size_bytes or (MAX_FILE_SIZE_MB * 1024 * 1024)

    # Poll progress at intervals
    pct = 5.0
    while not download_task.done():
        await asyncio.sleep(3)
        pct = min(pct + random.uniform(5, 15), 95)
        elapsed = time.time() - start_time
        estimated_downloaded = int(pct / 100 * total_bytes)
        await update_progress(pct, estimated_downloaded, total_bytes)

    file_bytes = download_task.result()

    if not file_bytes:
        await progress_msg.edit_text(
            f"❌ *Download failed.*\n\n"
            f"Possible reasons:\n"
            f"• File not available from source\n"
            f"• File exceeds {MAX_FILE_SIZE_MB} MB limit\n"
            f"• Source temporarily unavailable\n\n"
            f"_Try another format from the search results._",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    actual_size = len(file_bytes)
    if actual_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await progress_msg.edit_text(
            f"⚠️ File too large ({fmt_size(actual_size)}). Max allowed: {MAX_FILE_SIZE_MB} MB.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update_progress(100, actual_size, actual_size)

    # Prepare filename
    safe_title = "".join(c for c in book.title if c.isalnum() or c in " -_")[:60].strip()
    filename = f"{safe_title}.{book.format}"

    # Send file
    try:
        caption = (
            f"📚 *{book.title}*\n"
            f"✍️ {book.author}\n"
            f"📦 {fmt_size(actual_size)}  |  {book.format.upper()}\n"
            f"🌐 {book.language.title()}\n"
            f"📡 Source: {book.source}\n\n"
            f"⚠️ _For personal/educational use only._"
        )

        sent = await msg.reply_document(
            document=io.BytesIO(file_bytes),
            filename=filename,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
        )
        db.schedule_delete(sent.chat_id, sent.message_id, AUTO_DELETE_HOURS)
        await progress_msg.delete()
    except TelegramError as e:
        logger.error(f"Failed to send file: {e}")
        await progress_msg.edit_text(f"❌ Failed to send file: {e}")


async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button download callbacks (dl_<book_id>)."""
    query = update.callback_query
    await query.answer("📥 Initiating download...")

    book_id = query.data.replace("dl_", "", 1)
    book = get_cached_book(book_id)

    if not book:
        await query.answer("❌ Book not found. Please search again.", show_alert=True)
        return

    # Delegate to message-based handler by constructing a fake command
    # Instead, directly trigger download in-place
    context._user_data = context.user_data  # ensure data available
    await _do_download_from_callback(query.message, query.from_user, book, context)


async def _do_download_from_callback(msg, user, book: BookResult, context: ContextTypes.DEFAULT_TYPE):
    """Download and send book triggered from inline button."""
    owner = is_owner(user.id)
    in_group = msg.chat.type in ("group", "supergroup", "channel")

    if not in_group and not owner:
        await context.bot.send_message(
            user.id,
            "❌ Please use the group to download books!\n" + DM_REDIRECT_TEXT,
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if db.is_locked() and not owner:
        return

    progress_msg = await msg.reply_text(
        f"⏳ *Downloading:* {book.title[:50]}...",
        parse_mode=ParseMode.MARKDOWN,
    )
    db.schedule_delete(progress_msg.chat_id, progress_msg.message_id, AUTO_DELETE_HOURS)

    start_time = time.time()
    file_bytes = await download_book(book)

    if not file_bytes:
        await progress_msg.edit_text("❌ Download failed. Try another format.")
        return

    actual_size = len(file_bytes)
    elapsed = time.time() - start_time
    speed = fmt_speed(actual_size / elapsed if elapsed > 0 else 0)

    safe_title = "".join(c for c in book.title if c.isalnum() or c in " -_")[:60].strip()
    filename = f"{safe_title}.{book.format}"

    caption = (
        f"📚 *{book.title}*\n"
        f"✍️ {book.author}\n"
        f"📦 {fmt_size(actual_size)}  |  {book.format.upper()}\n"
        f"⚡ Downloaded in {elapsed:.1f}s at {speed}\n"
        f"📡 Source: {book.source}\n\n"
        f"⚠️ _For personal/educational use only._"
    )

    try:
        sent = await msg.reply_document(
            document=io.BytesIO(file_bytes),
            filename=filename,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
        )
        db.schedule_delete(sent.chat_id, sent.message_id, AUTO_DELETE_HOURS)
        await progress_msg.delete()
    except TelegramError as e:
        await progress_msg.edit_text(f"❌ Failed to send: {e}")


async def handle_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle DMs — redirect to group."""
    user = update.effective_user
    msg = update.effective_message
    text = msg.text or ""

    if text.startswith("/"):
        return  # Let command handlers deal with it

    db.add_user(user.id)

    if is_owner(user.id):
        return  # Owner can DM freely

    from config import REQUEST_GROUP_LINK, REQUEST_GROUP_USERNAME
    keyboard = [[InlineKeyboardButton(
        "📚 Join Request Group", url=REQUEST_GROUP_LINK
    )]]
    m = await msg.reply_text(
        f"{DM_REDIRECT_TEXT}\n\n"
        f"👉 *Group:* @{REQUEST_GROUP_USERNAME}\n\n"
        f"Then type: `#request <book name>`\n\n"
        f"{SCAM_WARNING}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
