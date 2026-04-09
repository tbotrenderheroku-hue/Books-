"""
Handles #request in group messages and /book_<id> download commands.
Fixes:
  - Markdown entity parse errors (escapes special chars in titles/authors)
  - Z-Library results now show first (source priority in aggregator)
  - Next/Previous page buttons for pagination
  - Archive.org invalid PDF validation (in openlibrary_source)
"""

import asyncio
import io
import logging
import re
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

# ─── Markdown helpers ─────────────────────────────────────────────────────────

_MD_SPECIAL = re.compile(r'([_*`\[\]()~>#+=|{}.!\\-])')


def esc(text: str) -> str:
    """Escape MarkdownV2 special characters to prevent parse errors."""
    return _MD_SPECIAL.sub(r'\\\1', str(text))


# ─── Utils ────────────────────────────────────────────────────────────────────

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


# ─── Result formatting ────────────────────────────────────────────────────────

def build_result_text(results: list[BookResult], page: int = 1, has_next: bool = False) -> str:
    """
    Build result message using MarkdownV2.
    Titles/authors are escaped to prevent BadRequest entity parse errors.
    /book_ commands are formatted as clickable inline code.
    """
    if not results:
        return "😔 *No books found\\.* Try a different keyword or author name\\."

    total = len(results)
    lines = [f"🔍 *Found {esc(str(total))} result\\(s\\) — Page {esc(str(page))}:*\n"]

    for book in results:
        emoji = FORMAT_EMOJI.get(book.format, "📄")
        source_tag = f"_{esc(book.source)}_"
        # Escape title and author — these often contain special chars like: . - ( ) *
        safe_title = esc(book.title)
        safe_author = esc(book.author)
        safe_lang = esc(book.language.title())
        safe_fmt = esc(book.format.upper())
        safe_size = esc(book.size_str)

        lines.append(
            f"📚 *{safe_title}*\n"
            f"✍️ {safe_author}\n"
            f"🌐 {safe_lang}  {emoji} {safe_fmt}  📦 {safe_size}\n"
            f"`/book_{esc(book.book_id)}`  {source_tag}\n"
        )

    lines.append("\n💡 Tap a `/book_\\.\\.\\.` command to download\\!")
    return "\n".join(lines)


def build_inline_buttons(
    results: list[BookResult],
    query: str,
    page: int,
    has_next: bool,
) -> InlineKeyboardMarkup:
    """Inline buttons: one download button per book + prev/next pagination."""
    keyboard = []
    for book in results:
        emoji = FORMAT_EMOJI.get(book.format, "📄")
        label = f"{emoji} {book.title[:26]}… ({book.format.upper()}, {book.size_str})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"dl_{book.book_id}")])

    # Pagination row
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(
            "⬅️ Prev", callback_data=f"page_{query}_{page - 1}"
        ))
    if has_next:
        nav.append(InlineKeyboardButton(
            "Next ➡️", callback_data=f"page_{query}_{page + 1}"
        ))
    if nav:
        keyboard.append(nav)

    return InlineKeyboardMarkup(keyboard)


# ─── Reaction ─────────────────────────────────────────────────────────────────

async def give_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reaction = random.choice(REACTIONS)
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.effective_message.message_id,
            reaction=[{"type": "emoji", "emoji": reaction}],
            is_big=True,
        )
    except Exception:
        pass


# ─── Group message handler ────────────────────────────────────────────────────

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
    if "#request" not in lower:
        return

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
    await _do_search(msg, query, page=1, context=context)


async def _do_search(
    msg: Message,
    query: str,
    page: int,
    context: ContextTypes.DEFAULT_TYPE,
    edit_msg: Message = None,
):
    """Search sources and send/edit result message."""
    searching_text = (
        f"🔍 Searching for: *{query}* (page {page})\n_Please wait..._"
    )

    if edit_msg:
        try:
            await edit_msg.edit_text(searching_text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        searching_msg = edit_msg
    else:
        searching_msg = await msg.reply_text(searching_text, parse_mode=ParseMode.MARKDOWN)
        db.schedule_delete(searching_msg.chat_id, searching_msg.message_id, AUTO_DELETE_HOURS)

    try:
        results = await search_all_sources(query, page=page)
    except Exception as e:
        logger.error(f"Search error: {e}")
        await searching_msg.edit_text("❌ Search failed. Please try again later.")
        return

    if not results:
        await searching_msg.edit_text(
            f"😔 *No books found for:* `{query}` (page {page})\n\nTry:\n• Different keywords\n• Author name\n• Partial title\n• Try page 1",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # We fetched 15 max — if we got 15, there's likely a next page
    has_next = len(results) >= 15

    result_text = build_result_text(results, page=page, has_next=has_next)
    inline = build_inline_buttons(results, query, page, has_next)

    try:
        await searching_msg.edit_text(
            result_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=inline,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"MarkdownV2 send failed: {e} — retrying as plain text")
        # Fallback: plain text (no formatting) to avoid losing results entirely
        plain = _build_plain_result(results, page)
        try:
            await searching_msg.edit_text(
                plain,
                reply_markup=inline,
                disable_web_page_preview=True,
            )
        except Exception as e2:
            logger.error(f"Plain text fallback also failed: {e2}")


def _build_plain_result(results: list[BookResult], page: int) -> str:
    lines = [f"Found {len(results)} result(s) — Page {page}:\n"]
    for book in results:
        emoji = FORMAT_EMOJI.get(book.format, "📄")
        lines.append(
            f"{emoji} {book.title}\n"
            f"   By: {book.author}\n"
            f"   Format: {book.format.upper()}  Size: {book.size_str}  [{book.source}]\n"
            f"   /book_{book.book_id}\n"
        )
    lines.append("\nTap /book_... to download!")
    return "\n".join(lines)


# ─── Pagination callback ──────────────────────────────────────────────────────

async def handle_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle page_<query>_<page> callbacks from inline buttons."""
    query_obj = update.callback_query
    await query_obj.answer("🔄 Loading page...")

    data = query_obj.data  # "page_<query>_<pagenum>"
    parts = data.split("_", 2)
    if len(parts) < 3:
        return

    _, search_query, page_str = parts
    try:
        page = int(page_str)
    except ValueError:
        return

    await _do_search(
        msg=query_obj.message,
        query=search_query,
        page=page,
        context=context,
        edit_msg=query_obj.message,
    )


# ─── Download via /book_<id> command ─────────────────────────────────────────

async def handle_book_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    text = msg.text or ""

    if not text.startswith("/book_"):
        return

    book_id = text[1:].split("@")[0].strip()
    book_id = book_id[len("book_"):]

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
        try:
            await progress_msg.edit_text(
                f"📥 *Downloading...*\n"
                f"📚 *{book.title[:40]}*\n\n"
                f"{bar}\n"
                f"📦 {fmt_size(downloaded)} / {fmt_size(total)}\n"
                f"⚡ Speed: `{fmt_speed(speed)}`\n"
                f"⏱ ETA: `{int(remaining)}s`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass

    await update_progress(0, 0, book.size_bytes)

    download_task = asyncio.create_task(download_book(book))
    total_bytes = book.size_bytes or (MAX_FILE_SIZE_MB * 1024 * 1024)

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
            f"⚠️ File too large ({fmt_size(actual_size)}). Max: {MAX_FILE_SIZE_MB} MB.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update_progress(100, actual_size, actual_size)

    safe_title = "".join(c for c in book.title if c.isalnum() or c in " -_")[:60].strip()
    filename = f"{safe_title}.{book.format}"

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


# ─── Inline button download callback ─────────────────────────────────────────

async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📥 Initiating download...")

    book_id = query.data.replace("dl_", "", 1)
    book = get_cached_book(book_id)

    if not book:
        await query.answer("❌ Book not found. Please search again.", show_alert=True)
        return

    await _do_download_from_callback(query.message, query.from_user, book, context)


async def _do_download_from_callback(msg, user, book: BookResult, context: ContextTypes.DEFAULT_TYPE):
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


# ─── DM redirect ─────────────────────────────────────────────────────────────

async def handle_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
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
        f"👉 *Group:* @{REQUEST_GROUP_USERNAME}\n\n"
        f"Then type: `#request <book name>`\n\n"
        f"{SCAM_WARNING}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    db.schedule_delete(m.chat_id, m.message_id, AUTO_DELETE_HOURS)
