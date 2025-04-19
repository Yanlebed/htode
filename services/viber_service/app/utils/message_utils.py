# services/viber_service/app/utils/message_utils.py

import logging
import asyncio
from typing import Optional, Union, Dict, Any, List
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage
from ..bot import viber

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

    Args:
        user_id: Viber user ID to send message to
        text: Message text
        keyboard: Optional keyboard (Viber keyboard dict)
        retry_count: Number of retry attempts in case of network errors
        retry_delay: Initial delay between retries in seconds (increases exponentially)

    Returns:
        The API response dict or None if all retries failed
    """
    messages = [TextMessage(text=text)]
    if keyboard:
        messages.append(KeyboardMessage(keyboard=keyboard))

    for attempt in range(retry_count):
        try:
            # Use run_in_executor to run the synchronous API call in a thread
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

    Args:
        user_id: Viber user ID
        image_url: URL of the image to send
        caption: Optional text caption for the image
        keyboard: Optional keyboard to include
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries in seconds

    Returns:
        The API response dict or None if all retries failed
    """
    messages = []
    if caption:
        messages.append(TextMessage(text=caption))

    messages.append(PictureMessage(media=image_url, text=caption or ""))

    if keyboard:
        messages.append(KeyboardMessage(keyboard=keyboard))

    for attempt in range(retry_count):
        try:
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
                return None

    return None