"""
Command handlers: /start, /help, /terms, /privacy, /sources,
/lock, /unlock, /broadcast, /restart
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import OWNER_IDS, REQUEST_GROUP_LINK, REQUEST_GROUP_USERNAME, START_IMAGE_URL, PRIVACY_POLICY_URL
from src.constants import (
    START_TEXT, HELP_TEXT, TERMS_AND_CONDITIONS, PRIVACY_POLICY,
    DISCLAIMER, SOURCES_TEXT, BOT_LOCKED_TEXT, DM_REDIRECT_TEXT
)
from src import database as db

logger = logging.getLogger(__name__)


def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


def _schedule(msg, context: ContextTypes.DEFAULT_TYPE):
    """Schedule a message for auto-deletion after 24h."""
    if msg:
        db.schedule_delete(msg.chat_id, msg.message_id)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    db.add_user(user.id)

    if db.is_locked() and not is_owner(user.id):
        m = await update.message.reply_text(BOT_LOCKED_TEXT, parse_mode=ParseMode.MARKDOWN)
        _schedule(m, context)
        return

    keyboard = [
        [
            InlineKeyboardButton("📚 Request Group", url=REQUEST_GROUP_LINK),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ],
        [
            InlineKeyboardButton("📜 Terms & Conditions", callback_data="terms"),
            InlineKeyboardButton("🔐 Privacy Policy", url=PRIVACY_POLICY_URL),
        ],
        [
            InlineKeyboardButton("⚠️ Disclaimer", callback_data="disclaimer"),
            InlineKeyboardButton("📡 Sources", callback_data="sources"),
        ],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    caption = START_TEXT + f"\n\n📌 Group: @{REQUEST_GROUP_USERNAME}"

    try:
        if START_IMAGE_URL and START_IMAGE_URL != "https://telegra.ph/file/your-start-image.jpg":
            msg = await update.message.reply_photo(
                photo=START_IMAGE_URL,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=markup,
            )
        else:
            msg = await update.message.reply_text(
                caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
    except Exception:
        msg = await update.message.reply_text(
            caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    _schedule(msg, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if db.is_locked() and not is_owner(update.effective_user.id):
        return
    m = await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    _schedule(m, context)


async def cmd_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text(TERMS_AND_CONDITIONS, parse_mode=ParseMode.MARKDOWN)
    _schedule(m, context)


async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text(PRIVACY_POLICY, parse_mode=ParseMode.MARKDOWN)
    _schedule(m, context)


async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text(SOURCES_TEXT, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    _schedule(m, context)


async def cmd_disclaimer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text(DISCLAIMER, parse_mode=ParseMode.MARKDOWN)
    _schedule(m, context)


# ─── OWNER COMMANDS ──────────────────────────────────────────────────────────

async def cmd_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    db.set_locked(True)
    m = await update.message.reply_text("🔒 Bot is now *LOCKED*. Only owners can use it.", parse_mode=ParseMode.MARKDOWN)
    _schedule(m, context)


async def cmd_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    db.set_locked(False)
    m = await update.message.reply_text("🔓 Bot is now *UNLOCKED* for all users.", parse_mode=ParseMode.MARKDOWN)
    _schedule(m, context)


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return

    if not context.args:
        m = await update.message.reply_text("Usage: `/broadcast Your message here`", parse_mode=ParseMode.MARKDOWN)
        _schedule(m, context)
        return

    text = " ".join(context.args)
    users = db.get_all_users()
    sent = 0
    failed = 0
    for uid in users:
        try:
            await context.bot.send_message(uid, text, parse_mode=ParseMode.MARKDOWN)
            sent += 1
        except Exception:
            failed += 1

    m = await update.message.reply_text(
        f"📢 Broadcast complete!\n✅ Sent: {sent}\n❌ Failed: {failed}",
        parse_mode=ParseMode.MARKDOWN
    )
    _schedule(m, context)


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    await update.message.reply_text("♻️ Restarting bot...")
    import os, sys
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ─── CALLBACK QUERY HANDLER ──────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    text_map = {
        "help": HELP_TEXT,
        "terms": TERMS_AND_CONDITIONS,
        "disclaimer": DISCLAIMER,
        "sources": SOURCES_TEXT,
        "privacy": PRIVACY_POLICY,
    }

    if data in text_map:
        try:
            await query.edit_message_caption(
                caption=text_map[data],
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_back_keyboard(),
            )
        except Exception:
            await query.edit_message_text(
                text=text_map[data],
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_back_keyboard(),
                disable_web_page_preview=True,
            )
    elif data == "back_start":
        keyboard = [
            [
                InlineKeyboardButton("📚 Request Group", url=REQUEST_GROUP_LINK),
                InlineKeyboardButton("❓ Help", callback_data="help"),
            ],
            [
                InlineKeyboardButton("📜 Terms", callback_data="terms"),
                InlineKeyboardButton("🔐 Privacy", callback_data="privacy"),
            ],
            [
                InlineKeyboardButton("⚠️ Disclaimer", callback_data="disclaimer"),
                InlineKeyboardButton("📡 Sources", callback_data="sources"),
            ],
        ]
        try:
            await query.edit_message_caption(
                caption=START_TEXT,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception:
            await query.edit_message_text(
                text=START_TEXT,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True,
            )


def _back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_start")]])
