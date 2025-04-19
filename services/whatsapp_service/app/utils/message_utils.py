# services/whatsapp_service/app/utils/message_utils.py

import logging
import asyncio
from typing import Optional, Union, Dict, Any, List
from ..bot import client, TWILIO_PHONE_NUMBER

logger = logging.getLogger(__name__)


async def safe_send_message(
        user_id: str,
        text: str,
        retry_count: int = 3,
        retry_delay: int = 1
) -> Optional[str]:
    """
    Safely send a text message with error handling and retries.

    Args:
        user_id: WhatsApp number (with or without whatsapp: prefix)
        text: Message text
        retry_count: Number of retry attempts in case of network errors
        retry_delay: Initial delay between retries in seconds (increases exponentially)

    Returns:
        The message SID if successful, None otherwise
    """
    # Ensure proper WhatsApp formatting
    if not user_id.startswith("whatsapp:"):
        user_id = f"whatsapp:{user_id}"

    for attempt in range(retry_count):
        try:
            # Use run_in_executor to run the synchronous API call in a thread
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    from_=TWILIO_PHONE_NUMBER,
                    body=text,
                    to=user_id
                )
            )
            return message.sid
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


async def safe_send_media(
        user_id: str,
        media_url: str,
        caption: Optional[str] = None,
        retry_count: int = 3,
        retry_delay: int = 1
) -> Optional[str]:
    """
    Safely send a media message with error handling and retries.

    Args:
        user_id: WhatsApp number
        media_url: URL of the media to send
        caption: Optional text caption
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries in seconds

    Returns:
        The message SID if successful, None otherwise
    """
    # Ensure proper WhatsApp formatting
    if not user_id.startswith("whatsapp:"):
        user_id = f"whatsapp:{user_id}"

    for attempt in range(retry_count):
        try:
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    from_=TWILIO_PHONE_NUMBER,
                    body=caption or "",
                    media_url=[media_url],
                    to=user_id
                )
            )
            return message.sid
        except Exception as e:
            if attempt < retry_count - 1:
                current_delay = retry_delay * (2 ** attempt)
                logger.warning(
                    f"Failed to send media (attempt {attempt + 1}/{retry_count}): {e}. Retrying in {current_delay}s")
                await asyncio.sleep(current_delay)
            else:
                logger.error(f"Failed to send media after {retry_count} attempts: {e}")
                return None

    return None