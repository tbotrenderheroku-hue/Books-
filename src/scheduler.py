"""
Background scheduler for:
- Auto-deleting messages after 24 hours
- Periodic cache cleanup
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.error import TelegramError

from src import database as db

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


def setup_scheduler(bot: Bot):
    @scheduler.scheduled_job("interval", minutes=10, id="auto_delete")
    async def auto_delete_messages():
        due = db.pop_due_deletes()
        for item in due:
            try:
                await bot.delete_message(
                    chat_id=item["chat_id"],
                    message_id=item["message_id"],
                )
            except TelegramError:
                pass  # Message may already be deleted
            except Exception as e:
                logger.warning(f"Delete error: {e}")

        if due:
            logger.info(f"Auto-deleted {len(due)} messages")

    scheduler.start()
    logger.info("✅ Scheduler started")
