# services/whatsapp_service/app/utils/message_utils.py

import logging
import asyncio
from typing import Optional, Union
from ..bot import client, TWILIO_PHONE_NUMBER
from common.messaging.utils import (
    safe_send_message as unified_send_message,
    safe_send_media as unified_send_media
)

logger = logging.getLogger(__name__)


async def safe_send_message(
        user_id: str,
        text: str,
        retry_count: int = 3,
        retry_delay: int = 1
) -> Optional[str]:
    """
    Safely send a text message with error handling and retries.
    This is a wrapper around the unified messaging utility.

    Args:
        user_id: WhatsApp number (with or without whatsapp: prefix)
        text: Message text
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries

    Returns:
        The message SID if successful, None otherwise
    """
    kwargs = {
        "retry_count": retry_count,
        "retry_delay": retry_delay,
        "platform": "whatsapp"
    }

    return await unified_send_message(user_id, text, **kwargs)


async def safe_send_media(
        user_id: str,
        media_url: str,
        caption: Optional[str] = None,
        retry_count: int = 3,
        retry_delay: int = 1
) -> Optional[str]:
    """
    Safely send a media message with error handling and retries.
    This is a wrapper around the unified messaging utility.

    Args:
        user_id: WhatsApp number
        media_url: URL of the media to send
        caption: Optional text caption
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries

    Returns:
        The message SID if successful, None otherwise
    """
    kwargs = {
        "retry_count": retry_count,
        "retry_delay": retry_delay,
        "platform": "whatsapp"
    }

    return await unified_send_media(user_id, media_url, caption, **kwargs)