# services/viber_service/app/utils/message_utils.py

from typing import Optional, Dict

from common.messaging.unified_platform_utils import (
    safe_send_message as unified_send_message,
    safe_send_media as unified_send_media
)

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from ... import logger


@log_operation("safe_send_message")
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
    with log_context(logger, user_id=user_id, message_type="text", has_keyboard=bool(keyboard)):
        # Add platform identifier and pass the keyboard via kwargs
        kwargs["platform"] = "viber"
        if keyboard:
            kwargs["keyboard"] = keyboard

        logger.debug(f"Sending text message to user {user_id}", extra={
            'text_length': len(text),
            'has_keyboard': bool(keyboard)
        })

        try:
            result = await unified_send_message(user_id, text, **kwargs)

            if result:
                logger.info(f"Successfully sent message to user {user_id}")
            else:
                logger.warning(f"Failed to send message to user {user_id}")

            return result
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}", exc_info=True, extra={
                'error_type': type(e).__name__,
                'text_length': len(text)
            })
            raise


@log_operation("safe_send_picture")
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
    with log_context(logger, user_id=user_id, message_type="picture", has_keyboard=bool(keyboard)):
        # Add platform identifier and pass the keyboard via kwargs
        kwargs["platform"] = "viber"
        if keyboard:
            kwargs["keyboard"] = keyboard

        logger.debug(f"Sending picture message to user {user_id}", extra={
            'image_url': image_url,
            'has_caption': bool(caption),
            'has_keyboard': bool(keyboard)
        })

        try:
            result = await unified_send_media(user_id, image_url, caption, **kwargs)

            if result:
                logger.info(f"Successfully sent picture to user {user_id}")
            else:
                logger.warning(f"Failed to send picture to user {user_id}")

            return result
        except Exception as e:
            logger.error(f"Error sending picture to user {user_id}", exc_info=True, extra={
                'error_type': type(e).__name__,
                'image_url': image_url
            })
            raise