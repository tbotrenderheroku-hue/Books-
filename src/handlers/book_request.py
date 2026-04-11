"""
Handles #request and #book in group messages, /book_<id> download commands.
All output uses HTML parse mode — no Markdown entity errors.
Includes sticker reactions for premium feel.
"""

import asyncio
import html as _html
import io
import logging
import random
import re
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from config import OWNER_IDS, REQUEST_GROUP_ID, MAX_FILE_SIZE_MB, AUTO_DELETE_HOURS
from src.constants import BOT_LOCKED_TEXT, DM_REDIRECT_TEXT, SCAM_WARNING, REACTIONS
from src import database as db
from src.sources import search_all_sources, get_cached_book, download_book, BookResult

logger = logging.getLogger(__name__)

HTML = ParseMode.HTML

FORMAT_EMOJI = {
    "pdf":  "📄", "epub": "📗", "mobi": "📘", "fb2":  "📙",
    "djvu": "📚", "azw3": "📕", "doc":  "📝", "txt":  "📃",
}

# Sticker file_ids — book / study themed (Telegram built-in animated emoji)
STICKER_SEARCHING = "CAACAgIAAxkBAAIBZWXoAAGOu3oMhpkYOzQr_Y6RzWlZAAIcAAMWQmsKqJXvWIYvxhY0AA"
STICKER_FOUND     = "CAACAgIAAxkBAAIBZmXoAAGRLVlqGGkn2B2e3Kv1_MOEAAI2AAMWQmsKn4W0AAGSZ1I0AA"
STICKER_FAIL      = "CAACAgIAAxkBAAIBZ2XoAAGT_g7-UMG8keTi8hJZLkfaAAI4AAMWQmsKbSq3HGf0mJw0AA"


# ── Helpers ──────────────────────────────────────────────────────────────────

def is_owner(uid: int) -> bool:
    return uid in OWNER_IDS


def fmt_size(b: int) -> str:
    if b == 0: return "Unknown"
    if b < 1024: return f"{b} B"
    if b < 1024**2: return f"{b/1024:.1f} KB"
    if b < 1024**3: return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"


def fmt_speed(bps: float) -> str:
    if bps < 1024: return f"{bps:.0f} B/s"
    if bps < 1024**2: return f"{bps/1024:.1f} KB/s"
    return f"{bps/1024**2:.1f} MB/s"


def progress_bar(pct: float, width: int = 12) -> str:
    filled = int(width * pct / 100)
    return f"[{'█'*filled}{'░'*(width-filled)}] {pct:.0f}%"


# ── Result formatting ─────────────────────────────────────────────────────────

def build_result_text(results: list[BookResult], page: int = 1) -> str:
    """Pure HTML — no Markdown, no entity errors, clickable /book_ commands."""
    if not results:
        return "😔 <b>No books found.</b> Try a different keyword or author name."

    lines = [f"🔍 <b>Found {len(results)} result(s) — Page {page}:</b>\n"]
    for book in results:
        emoji      = FORMAT_EMOJI.get(book.format, "📄")
        title      = _html.escape(book.title)
        author     = _html.escape(book.author)
        lang       = _html.escape(book.language.title())
        fmt        = _html.escape(book.format.upper())
        size       = _html.escape(book.size_str)
        source     = _html.escape(book.source)
        book_id    = _html.escape(book.book_id)

        lines.append(
            f"📚 <b>{title}</b>\n"
            f"✍️ {author}\n"
            f"🌐 {lang}  {emoji} {fmt}  📦 {size}\n"
            f"<code>/book_{book_id}</code>  <i>({source})</i>\n"
        )
    lines.append("\n💡 Tap a <code>/book_...</code> command to download!")
    return "\n".join(lines)


def build_buttons(results: list[BookResult], query: str, page: int, has_next: bool) -> InlineKeyboardMarkup:
    keyboard = []
    for book in results:
        emoji = FORMAT_EMOJI.get(book.format, "📄")
        label = f"{emoji} {book.title[:26]}… ({book.format.upper()}, {book.size_str})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"dl_{book.book_id}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{query}_{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton("Next ➡️",  callback_data=f"page_{query}_{page+1}"))
    if nav:
        keyboard.append(nav)
    return InlineKeyboardMarkup(keyboard)


# ── Reactions & stickers ──────────────────────────────────────────────────────

async def give_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.effective_message.message_id,
            reaction=[{"type": "emoji", "emoji": random.choice(REACTIONS)}],
            is_big=True,
        )
    except Exception:
        pass


async def send_sticker(chat_id, file_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Send a sticker silently — failure is non-critical."""
    try:
        msg = await context.bot.send_sticker(chat_id=chat_id, sticker=file_id)
        db.schedule_delete(msg.chat_id, msg.message_id, 2)  # auto-delete after 2h
    except Exception:
        pass  # sticker not critical


# ── Group message handler ─────────────────────────────────────────────────────

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg: Message = update.message or update.channel_post
    if not msg:
        return
    user = update.effective_user
    text = msg.text or msg.caption or ""

    if user and user.id != context.bot.id:
        asyncio.create_task(give_reaction(update, context))

    if REQUEST_GROUP_ID and msg.chat.id != REQUEST_GROUP_ID and not is_owner(user.id if user else 0):
        return
    if db.is_locked() and not is_owner(user.id if user else 0):
        return

    lower = text.lower()
    if "#request" not in lower and "#book" not in lower:
        return

    # Extract query — support both #request and #book
    if "#request" in lower:
        idx   = lower.index("#request")
        query = text[idx + len("#request"):].strip()
    else:
        idx   = lower.index("#book")
        query = text[idx + len("#book"):].strip()

    if not query:
        m = await msg.reply_text(
            "❓ Usage:\n"
            "<code>#request book name</code>\n"
            "<code>#book book name</code>\n\n"
            "Example: <code>#book Clean Code</code>",
            parse_mode=HTML,
        )
        db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
        return

    db.add_user(user.id)
    await _do_search(msg, query, page=1, context=context)


# ── Search ────────────────────────────────────────────────────────────────────

async def _do_search(
    msg: Message,
    query: str,
    page: int,
    context: ContextTypes.DEFAULT_TYPE,
    edit_msg: Message = None,
):
    searching_text = (
        f"🔍 Searching: <b>{_html.escape(query)}</b> (page {page})\n"
        f"<i>Please wait...</i>"
    )

    if edit_msg:
        try:
            await edit_msg.edit_text(searching_text, parse_mode=HTML)
        except Exception:
            pass
        searching_msg = edit_msg
    else:
        searching_msg = await msg.reply_text(searching_text, parse_mode=HTML)
        db.schedule_delete(searching_msg.chat_id, searching_msg.message_id, AUTO_DELETE_HOURS)

    try:
        results = await search_all_sources(query, page=page)
    except Exception as e:
        logger.error(f"Search error: {e}")
        await searching_msg.edit_text("❌ Search failed. Please try again later.", parse_mode=HTML)
        return

    if not results:
        await searching_msg.edit_text(
            f"😔 <b>No books found for:</b> <code>{_html.escape(query)}</code> (page {page})\n\n"
            f"Try:\n• Different keywords\n• Author name\n• Partial title",
            parse_mode=HTML,
        )
        return

    has_next = len(results) >= 15
    result_text = build_result_text(results, page=page)
    inline      = build_buttons(results, query, page, has_next)

    try:
        await searching_msg.edit_text(
            result_text,
            parse_mode=HTML,
            reply_markup=inline,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Result send failed: {e}")


# ── Pagination callback ───────────────────────────────────────────────────────

async def handle_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("🔄 Loading...")
    parts = q.data.split("_", 2)
    if len(parts) < 3:
        return
    _, search_query, page_str = parts
    try:
        page = int(page_str)
    except ValueError:
        return
    await _do_search(q.message, search_query, page=page, context=context, edit_msg=q.message)


# ── Download via /book_<id> ───────────────────────────────────────────────────

async def handle_book_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg  = update.effective_message
    user = update.effective_user
    text = msg.text or ""
    if not text.startswith("/book_"):
        return

    raw     = text[1:].split("@")[0].strip()
    book_id = raw[len("book_"):]

    in_group = msg.chat.type in ("group", "supergroup", "channel")
    owner    = is_owner(user.id)

    if not in_group and not owner:
        m = await msg.reply_text(
            "❌ Please request books in the group, not in DMs!\n\n" + DM_REDIRECT_TEXT,
            parse_mode=HTML,
        )
        db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
        return

    if db.is_locked() and not owner:
        m = await msg.reply_text(BOT_LOCKED_TEXT, parse_mode=HTML)
        db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
        return

    book = get_cached_book(book_id)
    if not book:
        m = await msg.reply_text(
            "❌ Book expired from cache.\n"
            "Please search again with <code>#book title</code>",
            parse_mode=HTML,
        )
        db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
        return

    progress_msg = await msg.reply_text(
        f"⏳ <b>Preparing download...</b>\n"
        f"📚 {_html.escape(book.title)}\n"
        f"✍️ {_html.escape(book.author)}",
        parse_mode=HTML,
    )
    db.schedule_delete(progress_msg.chat_id, progress_msg.message_id, AUTO_DELETE_HOURS)

    start_time = time.time()

    async def update_progress(pct: float, downloaded: int, total: int):
        elapsed   = time.time() - start_time
        speed     = downloaded / elapsed if elapsed > 0 else 0
        remaining = (total - downloaded) / speed if speed > 0 and total > 0 else 0
        bar       = progress_bar(pct)
        try:
            await progress_msg.edit_text(
                f"📥 <b>Downloading...</b>\n"
                f"📚 <b>{_html.escape(book.title[:40])}</b>\n\n"
                f"{bar}\n"
                f"📦 {fmt_size(downloaded)} / {fmt_size(total)}\n"
                f"⚡ Speed: <code>{fmt_speed(speed)}</code>\n"
                f"⏱ ETA: <code>{int(remaining)}s</code>",
                parse_mode=HTML,
            )
        except Exception:
            pass

    await update_progress(0, 0, book.size_bytes)

    download_task = asyncio.create_task(download_book(book))
    total_bytes   = book.size_bytes or (MAX_FILE_SIZE_MB * 1024 * 1024)
    pct = 5.0
    while not download_task.done():
        await asyncio.sleep(3)
        pct = min(pct + random.uniform(5, 15), 95)
        estimated = int(pct / 100 * total_bytes)
        await update_progress(pct, estimated, total_bytes)

    file_bytes = download_task.result()

    if not file_bytes:
        await progress_msg.edit_text(
            f"❌ <b>Download failed.</b>\n\n"
            f"Reasons:\n"
            f"• File not available from source\n"
            f"• Exceeds {MAX_FILE_SIZE_MB} MB limit\n"
            f"• Source temporarily unavailable\n\n"
            f"<i>Try another format from search results.</i>",
            parse_mode=HTML,
        )
        return

    actual_size = len(file_bytes)
    if actual_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await progress_msg.edit_text(
            f"⚠️ File too large ({fmt_size(actual_size)}). Max: {MAX_FILE_SIZE_MB} MB.",
            parse_mode=HTML,
        )
        return

    await update_progress(100, actual_size, actual_size)

    safe_title = "".join(c for c in book.title if c.isalnum() or c in " -_")[:60].strip()
    filename   = f"{safe_title}.{book.format}"

    try:
        caption = (
            f"📚 <b>{_html.escape(book.title)}</b>\n"
            f"✍️ {_html.escape(book.author)}\n"
            f"📦 {fmt_size(actual_size)}  |  {book.format.upper()}\n"
            f"🌐 {book.language.title()}\n"
            f"📡 Source: {_html.escape(book.source)}\n\n"
            f"⚠️ <i>For personal/educational use only.</i>"
        )
        sent = await msg.reply_document(
            document=io.BytesIO(file_bytes),
            filename=filename,
            caption=caption,
            parse_mode=HTML,
        )
        db.schedule_delete(sent.chat_id, sent.message_id, AUTO_DELETE_HOURS)
        await progress_msg.delete()

        # Premium sticker after successful download
        asyncio.create_task(
            send_sticker(msg.chat_id, STICKER_FOUND, context)
        )

    except TelegramError as e:
        logger.error(f"File send failed: {e}")
        await progress_msg.edit_text(f"❌ Failed to send file: {e}", parse_mode=HTML)


# ── Inline button download ────────────────────────────────────────────────────

async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📥 Starting download...")
    book_id = query.data.replace("dl_", "", 1)
    book    = get_cached_book(book_id)
    if not book:
        await query.answer("❌ Book expired. Search again.", show_alert=True)
        return
    await _do_download_from_callback(query.message, query.from_user, book, context)


async def _do_download_from_callback(msg, user, book: BookResult, context: ContextTypes.DEFAULT_TYPE):
    owner    = is_owner(user.id)
    in_group = msg.chat.type in ("group", "supergroup", "channel")
    if not in_group and not owner:
        await context.bot.send_message(
            user.id,
            "❌ Please use the group to download!\n" + DM_REDIRECT_TEXT,
            parse_mode=HTML,
        )
        return
    if db.is_locked() and not owner:
        return

    progress_msg = await msg.reply_text(
        f"⏳ <b>Downloading:</b> {_html.escape(book.title[:50])}...",
        parse_mode=HTML,
    )
    db.schedule_delete(progress_msg.chat_id, progress_msg.message_id, AUTO_DELETE_HOURS)

    start_time = time.time()
    file_bytes = await download_book(book)

    if not file_bytes:
        await progress_msg.edit_text("❌ Download failed. Try another format.", parse_mode=HTML)
        return

    actual_size = len(file_bytes)
    elapsed     = time.time() - start_time
    speed       = fmt_speed(actual_size / elapsed if elapsed > 0 else 0)
    safe_title  = "".join(c for c in book.title if c.isalnum() or c in " -_")[:60].strip()
    filename    = f"{safe_title}.{book.format}"

    caption = (
        f"📚 <b>{_html.escape(book.title)}</b>\n"
        f"✍️ {_html.escape(book.author)}\n"
        f"📦 {fmt_size(actual_size)}  |  {book.format.upper()}\n"
        f"⚡ {elapsed:.1f}s at {speed}\n"
        f"📡 Source: {_html.escape(book.source)}\n\n"
        f"⚠️ <i>For personal/educational use only.</i>"
    )
    try:
        sent = await msg.reply_document(
            document=io.BytesIO(file_bytes),
            filename=filename,
            caption=caption,
            parse_mode=HTML,
        )
        db.schedule_delete(sent.chat_id, sent.message_id, AUTO_DELETE_HOURS)
        await progress_msg.delete()
        asyncio.create_task(send_sticker(msg.chat_id, STICKER_FOUND, context))
    except TelegramError as e:
        await progress_msg.edit_text(f"❌ Failed to send: {e}", parse_mode=HTML)


# ── DM redirect ───────────────────────────────────────────────────────────────

async def handle_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg  = update.effective_message
    text = msg.text or ""
    if text.startswith("/"):
        return
    db.add_user(user.id)
    if is_owner(user.id):
        return
    from config import REQUEST_GROUP_LINK, REQUEST_GROUP_USERNAME
    keyboard = [[InlineKeyboardButton("📚 Join Request Group", url=REQUEST_GROUP_LINK)]]
    m = await msg.reply_text(
        f"{DM_REDIRECT_TEXT}\n\n"
        f"👉 <b>Group:</b> @{REQUEST_GROUP_USERNAME}\n\n"
        f"Then type: <code>#book book name</code>\n\n"
        f"{SCAM_WARNING}",
        parse_mode=HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
