# services/telegram_service/app/tasks.py

import asyncio
from common.celery_app import celery_app  # Импортируем общий Celery экземпляр
from .bot import bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
# from aiogram.utils.markdown import escape_md
import logging


@celery_app.task(name="telegram_service.app.tasks.send_message_task")
def send_message_task(user_id, text, image_url=None, resource_url=None):
    async def send():
        logging.info('Sending message to user...')
        try:
            logging.info('Sending text...')
            buttons = InlineKeyboardMarkup().add(
                InlineKeyboardButton("Подробнее", url=resource_url)
            )
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=buttons
            )
            # if image_url and resource_url:
            #     logging.info('Sending photo...')
            #     buttons = InlineKeyboardMarkup().add(
            #         InlineKeyboardButton("Подробнее", url=resource_url)
            #     )
            #     await bot.send_photo(
            #         chat_id=user_id,
            #         photo=image_url,
            #         caption=text,
            #         parse_mode='Markdown',
            #         reply_markup=buttons
            #     )
            # else:
            #     logging.info('Sending text...')
            #     await bot.send_message(
            #         chat_id=user_id,
            #         text=text,
            #         parse_mode='Markdown'
            #     )
        except Exception as e:
            # Логирование ошибок при отправке сообщений
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send message to user {user_id}: {e}")

    asyncio.run(send())
    return True
