# services/whatsapp_service/app/utils/message_utils.py

import logging
from typing import Optional

from common.messaging.unified_platform_utils import (
    safe_send_message as unified_send_message,
    safe_send_media as unified_send_media
)
from ..bot import sanitize_phone_number

logger = logging.getLogger(__name__)


async def safe_send_message(
        user_id: str,
        text: str,
        **kwargs
) -> Optional[str]:
    """
    WhatsApp-specific wrapper for the unified send_message utility.

    Args:
        user_id: WhatsApp number (with or without whatsapp: prefix)
        text: Message text
        **kwargs: Additional parameters

    Returns:
        Message SID or None if failed
    """
    # Sanitize phone number and set platform
    user_id = sanitize_phone_number(user_id)
    kwargs["platform"] = "whatsapp"

    return await unified_send_message(user_id, text, **kwargs)


async def safe_send_media(
        user_id: str,
        media_url: str,
        caption: Optional[str] = None,
        **kwargs
) -> Optional[str]:
    """
    WhatsApp-specific wrapper for the unified send_media utility.

    Args:
        user_id: WhatsApp number
        media_url: URL of the media to send
        caption: Optional text caption
        **kwargs: Additional parameters

    Returns:
        Message SID or None if failed
    """
    # Sanitize phone number and set platform
    user_id = sanitize_phone_number(user_id)
    kwargs["platform"] = "whatsapp"

    return await unified_send_media(user_id, media_url, caption, **kwargs)