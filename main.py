"""
BookFinderBot — Main Entry Point
"""

import logging
import os
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import config
from src.handlers.commands import (
    cmd_start, cmd_help, cmd_terms, cmd_privacy, cmd_sources, cmd_disclaimer,
    cmd_lock, cmd_unlock, cmd_broadcast, cmd_restart,
    callback_handler,
)
from src.handlers.book_request import (
    handle_group_message,
    handle_book_download,
    handle_download_callback,
    handle_pagination_callback,
    handle_dm,
)
from src.scheduler import setup_scheduler

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    setup_scheduler(application.bot)
    logger.info(f"✅ Bot @{(await application.bot.get_me()).username} is running!")


def main():
    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Core commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("terms", cmd_terms))
    app.add_handler(CommandHandler("privacy", cmd_privacy))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("disclaimer", cmd_disclaimer))
    app.add_handler(CommandHandler("restart", cmd_restart))

    # Owner commands
    app.add_handler(CommandHandler("lock", cmd_lock))
    app.add_handler(CommandHandler("unlock", cmd_unlock))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # Book download (/book_<id>)
    app.add_handler(MessageHandler(
        filters.Regex(r"^/book_") & (filters.ChatType.GROUPS | filters.ChatType.PRIVATE),
        handle_book_download,
    ))

    # Group #request messages
    app.add_handler(MessageHandler(
        (filters.ChatType.GROUPS | filters.ChatType.CHANNEL) & filters.TEXT,
        handle_group_message,
    ))

    # DM handler
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_dm,
    ))

    # Pagination callbacks (page_<query>_<page>)
    app.add_handler(CallbackQueryHandler(handle_pagination_callback, pattern=r"^page_"))

    # Download callbacks (dl_<book_id>)
    app.add_handler(CallbackQueryHandler(handle_download_callback, pattern=r"^dl_"))

    # Other callbacks (help, terms, sources, etc.)
    app.add_handler(CallbackQueryHandler(callback_handler))

    if config.USE_WEBHOOK and config.WEBHOOK_URL:
        logger.info(f"Starting in WEBHOOK mode on port {config.PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=config.PORT,
            url_path=config.BOT_TOKEN,
            webhook_url=f"{config.WEBHOOK_URL}/{config.BOT_TOKEN}",
        )
    else:
        logger.info("Starting in POLLING mode")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
