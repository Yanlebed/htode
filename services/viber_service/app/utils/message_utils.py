# services/viber_service/app/utils/message_utils.py

import logging
from typing import Optional, Dict

from common.messaging.unified_platform_utils import (
    safe_send_message as unified_send_message,
    safe_send_media as unified_send_media
)

logger = logging.getLogger(__name__)


async def safe_send_message(
        user_id: str,
        text: str,
        keyboard: Optional[Dict] = None,
        **kwargs
) -> Optional[Dict]:
    """
    Viber-specific wrapper for the unified send_message utility.

    Args:
        user_id: Viber user ID
        text: Message text
        keyboard: Optional Viber keyboard dict
        **kwargs: Additional parameters

    Returns:
        Response dict or None if failed
    """
    # Add platform identifier and pass the keyboard via kwargs
    kwargs["platform"] = "viber"
    if keyboard:
        kwargs["keyboard"] = keyboard

    return await unified_send_message(user_id, text, **kwargs)


async def safe_send_picture(
        user_id: str,
        image_url: str,
        caption: Optional[str] = None,
        keyboard: Optional[Dict] = None,
        **kwargs
) -> Optional[Dict]:
    """
    Viber-specific wrapper for the unified send_media utility.

    Args:
        user_id: Viber user ID
        image_url: Image URL
        caption: Optional caption
        keyboard: Optional Viber keyboard dict
        **kwargs: Additional parameters

    Returns:
        Response dict or None if failed
    """
    # Add platform identifier and pass the keyboard via kwargs
    kwargs["platform"] = "viber"
    if keyboard:
        kwargs["keyboard"] = keyboard

    return await unified_send_media(user_id, image_url, caption, **kwargs)