# services/viber_service/app/utils/message_utils.py

import logging
import asyncio
from typing import Optional, Dict, Any
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage
from ..bot import viber
from common.messaging.utils import (
    safe_send_message as unified_send_message,
    safe_send_media as unified_send_media
)

logger = logging.getLogger(__name__)


async def safe_send_message(
        user_id: str,
        text: str,
        keyboard: Optional[Dict] = None,
        retry_count: int = 3,
        retry_delay: int = 1
) -> Optional[Dict]:
    """
    Safely send a text message with error handling and retries.
    This is a wrapper around the unified messaging utility.

    Args:
        user_id: Viber user ID to send message to
        text: Message text
        keyboard: Optional keyboard (Viber keyboard dict)
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries

    Returns:
        The API response dict or None if all retries failed
    """
    kwargs = {
        "keyboard": keyboard,
        "retry_count": retry_count,
        "retry_delay": retry_delay,
        "platform": "viber"
    }

    return await unified_send_message(user_id, text, **kwargs)


async def safe_send_picture(
        user_id: str,
        image_url: str,
        caption: Optional[str] = None,
        keyboard: Optional[Dict] = None,
        retry_count: int = 3,
        retry_delay: int = 1
) -> Optional[Dict]:
    """
    Safely send a picture message with error handling and retries.
    This is a wrapper around the unified messaging utility.

    Args:
        user_id: Viber user ID
        image_url: URL of the image to send
        caption: Optional text caption for the image
        keyboard: Optional keyboard dict
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries

    Returns:
        The API response dict or None if all retries failed
    """
    kwargs = {
        "keyboard": keyboard,
        "retry_count": retry_count,
        "retry_delay": retry_delay,
        "platform": "viber"
    }

    return await unified_send_media(user_id, image_url, caption, **kwargs)