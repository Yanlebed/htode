# services/telegram_service/app/tasks.py

import asyncio
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MediaGroup
from common.celery_app import celery_app
from .bot import bot

logger = logging.getLogger(__name__)


@celery_app.task(name="telegram_service.app.tasks.send_message_task")
def send_message_task(user_id, text, image_url=None, resource_url=None):
    async def send():
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


@celery_app.task(name="telegram_service.app.tasks.send_ad_with_photos")
def send_ad_with_photos(user_id, text, image_urls, resource_url=None):
    async def send(message_text):
        logger.info(f"Sending message with photos to user {user_id}...")

        # If there's a resource_url, incorporate it into the text
        if resource_url:
            # Use Markdown
            message_text += f"\n\n[>>>ВІДКРИТИ ОГОЛОШЕННЯ<<<]({resource_url})"
            parse_mode = "Markdown"
        else:
            parse_mode = None  # or "Markdown" if you want formatting anyway

        if len(image_urls) > 1:
            # multiple images -> media group
            media = MediaGroup()
            for i, url in enumerate(image_urls[:10]):  # up to 10
                if i == 0:
                    # first item with a caption
                    media.attach_photo(
                        url,
                        caption=message_text,
                        parse_mode=parse_mode
                    )
                else:
                    media.attach_photo(url)
            await bot.send_media_group(chat_id=user_id, media=media)

        else:
            # single or zero images
            if image_urls:
                # exactly 1 image
                image_url = image_urls[0]
                await bot.send_photo(
                    chat_id=user_id,
                    photo=image_url,
                    caption=message_text,
                    parse_mode=parse_mode
                )
            else:
                # no images
                await bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    parse_mode=parse_mode
                )

    asyncio.run(send(text))
    return True
