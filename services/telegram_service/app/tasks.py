# services/telegram_service/app/tasks.py

import asyncio
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from common.celery_app import celery_app
from .bot import bot

@celery_app.task(name="telegram_service.app.tasks.send_message_task")
def send_message_task(user_id, text, image_url=None, resource_url=None):
    async def send():
        logger = logging.getLogger(__name__)
        logger.info(f"Sending message to user {user_id}...")

        # Build an inline keyboard if resource_url is present
        buttons = None
        if resource_url:
            buttons = InlineKeyboardMarkup().add(
                InlineKeyboardButton("Відкрити оголошення", url=resource_url)
            )

        try:
            if image_url:
                logger.info("Sending photo + caption + button.")
                await bot.send_photo(
                    chat_id=user_id,
                    photo=image_url,
                    caption=text,
                    parse_mode='Markdown',
                    reply_markup=buttons
                )
            else:
                logger.info("Sending text message (no photo).")
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode='Markdown',
                    reply_markup=buttons
                )
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")

    asyncio.run(send())
    return True
