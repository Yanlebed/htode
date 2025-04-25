# services/viber_service/app/utils/message_utils.py

import logging
import asyncio
from typing import Optional, Dict, Any
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage
from ..bot import viber
from common.messaging.service import messaging_service

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
    Now uses the unified messaging service when possible.

    Args:
        user_id: Viber user ID to send message to
        text: Message text
        keyboard: Optional keyboard (Viber keyboard dict)
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries

    Returns:
        The API response dict or None if all retries failed
    """
    try:
        # Get the user's database ID (for messaging service)
        from common.db.models import get_db_user_id_by_telegram_id
        db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type="viber")

        if db_user_id:
            # Use messaging service if we have a database user ID
            kwargs = {
                "keyboard": keyboard
            }

            success = await messaging_service.send_notification(
                user_id=db_user_id,
                text=text,
                **kwargs
            )

            if success:
                return {"status": "success"}

        # Fall back to direct Viber API usage
        messages = [TextMessage(text=text)]

        if keyboard:
            messages.append(KeyboardMessage(keyboard=keyboard))

        for attempt in range(retry_count):
            try:
                # Run in thread pool since Viber API is synchronous
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: viber.send_messages(user_id, messages)
                )
                return response
            except Exception as e:
                if attempt < retry_count - 1:
                    # Exponential backoff
                    current_delay = retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Failed to send message (attempt {attempt + 1}/{retry_count}): {e}. Retrying in {current_delay}s")
                    await asyncio.sleep(current_delay)
                else:
                    logger.error(f"Failed to send message after {retry_count} attempts: {e}")
                    return None

    except Exception as e:
        logger.error(f"Error in safe_send_message: {e}")
        return None


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
    Now uses the unified messaging service when possible.

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
    try:
        # Get the user's database ID (for messaging service)
        from common.db.models import get_db_user_id_by_telegram_id
        db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type="viber")

        if db_user_id:
            # Use messaging service if we have a database user ID
            kwargs = {
                "keyboard": keyboard
            }

            success = await messaging_service.send_notification(
                user_id=db_user_id,
                text=caption,
                image_url=image_url,
                **kwargs
            )

            if success:
                return {"status": "success"}

        # Fall back to direct Viber API usage
        messages = []

        # Add caption as separate text message if provided
        if caption:
            messages.append(TextMessage(text=caption))

        # Add the image
        messages.append(PictureMessage(
            media=image_url,
            text=caption or ""
        ))

        # Add keyboard if provided
        if keyboard:
            messages.append(KeyboardMessage(keyboard=keyboard))

        for attempt in range(retry_count):
            try:
                # Run in thread pool since Viber API is synchronous
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: viber.send_messages(user_id, messages)
                )
                return response
            except Exception as e:
                if attempt < retry_count - 1:
                    current_delay = retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Failed to send picture (attempt {attempt + 1}/{retry_count}): {e}. Retrying in {current_delay}s")
                    await asyncio.sleep(current_delay)
                else:
                    logger.error(f"Failed to send picture after {retry_count} attempts: {e}")
                    # Try sending just text if image fails
                    if caption:
                        return await safe_send_message(user_id, f"{caption}\n\n[Image URL: {image_url}]", keyboard)
                    return None

    except Exception as e:
        logger.error(f"Error in safe_send_picture: {e}")
        return None