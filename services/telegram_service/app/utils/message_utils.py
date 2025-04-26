# services/telegram_service/app/utils/message_utils.py

import logging
from typing import Optional, Union, Dict, Any
from aiogram.types import Message, InputFile

from common.messaging.unified_platform_utils import (
    safe_send_message as unified_send_message,
    safe_send_media as unified_send_media,
    safe_edit_message_telegram,
    safe_answer_callback_query_telegram,
    delete_message_safe_telegram
)

logger = logging.getLogger(__name__)


# Re-export the centralized utilities with Telegram-specific defaults
async def safe_send_message(
        chat_id: Union[int, str],
        text: str,
        **kwargs
) -> Optional[Message]:
    """
    Telegram-specific wrapper for the unified send_message utility.

    Args:
        chat_id: Telegram chat ID
        text: Message text
        **kwargs: Additional parameters

    Returns:
        The message object or None if failed
    """
    # Add platform identifier
    kwargs["platform"] = "telegram"
    return await unified_send_message(chat_id, text, **kwargs)


async def safe_send_photo(
        chat_id: Union[int, str],
        photo: Union[str, InputFile],
        caption: Optional[str] = None,
        **kwargs
) -> Optional[Message]:
    """
    Telegram-specific wrapper for the unified send_media utility.

    Args:
        chat_id: Telegram chat ID
        photo: Photo URL or InputFile
        caption: Optional photo caption
        **kwargs: Additional parameters

    Returns:
        The message object or None if failed
    """
    # Only handle URL-based photos in the unified way
    if isinstance(photo, str):
        # Add platform identifier
        kwargs["platform"] = "telegram"
        return await unified_send_media(chat_id, photo, caption, **kwargs)
    else:
        # For InputFile, we need to use the Telegram bot directly
        from ..bot import bot
        try:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Error sending photo with InputFile: {e}")
            return None


# Re-export other utility functions
async def safe_edit_message(
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        **kwargs
) -> Optional[Message]:
    """Telegram-specific wrapper for edit_message utility."""
    return await safe_edit_message_telegram(chat_id, message_id, text, **kwargs)


async def safe_answer_callback_query(
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
) -> bool:
    """Telegram-specific wrapper for answer_callback_query utility."""
    return await safe_answer_callback_query_telegram(callback_query_id, text, show_alert)


async def delete_message_safe(
        chat_id: Union[int, str],
        message_id: int
) -> bool:
    """Telegram-specific wrapper for delete_message utility."""
    return await delete_message_safe_telegram(chat_id, message_id)