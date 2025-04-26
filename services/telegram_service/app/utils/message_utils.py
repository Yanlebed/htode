# services/telegram_service/app/utils/message_utils.py

import logging
import asyncio
from typing import Optional, Union, Dict, Any
from aiogram.types import InlineKeyboardMarkup, ParseMode, Message, InputFile
from ..bot import bot
from common.messaging.utils import (
    safe_send_message as unified_send_message,
    safe_send_media as unified_send_media,
    safe_edit_message_telegram,
    safe_answer_callback_query_telegram,
    delete_message_safe_telegram
)

logger = logging.getLogger(__name__)

async def safe_send_message(
        chat_id: Union[int, str],
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        disable_web_page_preview: bool = False,
        retry_count: int = 3,
        retry_delay: int = 1
) -> Optional[Message]:
    """
    Safely send a message with error handling and retries.
    This is a wrapper around the unified messaging utility.

    Args:
        chat_id: User or chat ID to send message to
        text: Message text
        parse_mode: Optional parse mode (Markdown or HTML)
        reply_markup: Optional reply markup (keyboard)
        disable_web_page_preview: Whether to disable web page preview
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries

    Returns:
        The sent Message object or None if all retries failed
    """
    kwargs = {
        "parse_mode": parse_mode,
        "reply_markup": reply_markup,
        "disable_web_page_preview": disable_web_page_preview,
        "retry_count": retry_count,
        "retry_delay": retry_delay,
        "platform": "telegram"
    }

    return await unified_send_message(chat_id, text, **kwargs)


async def safe_send_photo(
        chat_id: Union[int, str],
        photo: Union[str, InputFile],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        retry_count: int = 3,
        retry_delay: int = 1
) -> Optional[Message]:
    """
    Safely send a photo with error handling and retries.
    This is a wrapper around the unified messaging utility.

    Args:
        chat_id: User or chat ID to send photo to
        photo: Photo URL or InputFile
        caption: Optional photo caption
        parse_mode: Optional parse mode for caption
        reply_markup: Optional reply markup (keyboard)
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries

    Returns:
        The sent Message object or None if all retries failed
    """
    # Only handle URL-based photos in the unified way
    # For InputFile, we need a separate implementation since it's Telegram-specific
    if isinstance(photo, str):
        kwargs = {
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
            "retry_count": retry_count,
            "retry_delay": retry_delay,
            "platform": "telegram"
        }

        return await unified_send_media(chat_id, photo, caption, **kwargs)
    else:
        # Special handling for InputFile since it's Telegram-specific
        # We use a simplified retry logic here
        for attempt in range(retry_count):
            try:
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            except Exception as e:
                if attempt < retry_count - 1:
                    logger.warning(f"Error sending photo (attempt {attempt+1}/{retry_count}): {e}")
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                else:
                    logger.error(f"Failed to send photo after {retry_count} attempts: {e}")
                    return None


# These functions use the centralized telegram helpers
async def safe_edit_message(
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        disable_web_page_preview: bool = False
) -> Optional[Message]:
    """
    Safely edit a message with error handling.
    This is a wrapper around the platform-specific function.
    """
    return await safe_edit_message_telegram(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
        disable_web_page_preview=disable_web_page_preview
    )


async def safe_answer_callback_query(
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
) -> bool:
    """
    Safely answer a callback query with error handling.
    This is a wrapper around the platform-specific function.
    """
    return await safe_answer_callback_query_telegram(
        callback_query_id=callback_query_id,
        text=text,
        show_alert=show_alert
    )


async def delete_message_safe(
        chat_id: Union[int, str],
        message_id: int
) -> bool:
    """
    Safely delete a message with error handling.
    This is a wrapper around the platform-specific function.
    """
    return await delete_message_safe_telegram(
        chat_id=chat_id,
        message_id=message_id
    )