# services/telegram_service/app/utils/message_utils.py

import logging
import asyncio
from typing import Optional, Union, Dict, Any
from aiogram.types import InlineKeyboardMarkup, ParseMode, Message, CallbackQuery, InputMedia, InputFile
from aiogram.utils.exceptions import (
    MessageNotModified, BotBlocked, ChatNotFound,
    UserDeactivated, TelegramAPIError, RetryAfter,
    InvalidQueryID, MessageToDeleteNotFound
)
from ..bot import bot
from common.messaging.service import messaging_service

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
    Now leverages the unified messaging service for better consistency.

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
    try:
        # For backward compatibility, convert chat_id to string if it's an integer
        user_id = str(chat_id)

        # Get the user's database ID (for messaging service)
        from common.db.models import get_db_user_id_by_telegram_id
        db_user_id = get_db_user_id_by_telegram_id(user_id)

        if db_user_id:
            # Use messaging service if we have a database user ID
            kwargs = {
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "disable_web_page_preview": disable_web_page_preview
            }

            success = await messaging_service.send_notification(
                user_id=db_user_id,
                text=text,
                **kwargs
            )

            if success:
                # If needed, we could fetch and return the sent message,
                # but for now we'll return a simple indicator of success
                return True

        # Fall back to direct bot usage if no database user ID found
        # or for backward compatibility
        for attempt in range(retry_count):
            try:
                return await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview
                )
            except RetryAfter as e:
                # Respect Telegram's rate limiting
                logger.warning(f"Rate limit exceeded. Retrying in {e.timeout} seconds.")
                await asyncio.sleep(e.timeout)
                # Don't count this as an attempt since it's just rate limiting
                continue
            except (BotBlocked, ChatNotFound, UserDeactivated) as e:
                # These are permanent errors, no need to retry
                logger.warning(f"Permanent error when sending message to {chat_id}: {e}")
                return None
            except TelegramAPIError as e:
                # For other Telegram API errors, we'll retry with backoff
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
    Now uses the unified messaging service when possible.

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
    try:
        # For backward compatibility, convert chat_id to string if it's an integer
        user_id = str(chat_id)

        # Get the user's database ID (for messaging service)
        from common.db.models import get_db_user_id_by_telegram_id
        db_user_id = get_db_user_id_by_telegram_id(user_id)

        if db_user_id and isinstance(photo, str):
            # Use messaging service if we have a database user ID and photo is a URL
            kwargs = {
                "parse_mode": parse_mode,
                "reply_markup": reply_markup
            }

            success = await messaging_service.send_notification(
                user_id=db_user_id,
                text=caption,
                image_url=photo,
                **kwargs
            )

            if success:
                return True

        # Fall back to direct bot usage
        for attempt in range(retry_count):
            try:
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            except RetryAfter as e:
                logger.warning(f"Rate limit exceeded. Retrying in {e.timeout} seconds.")
                await asyncio.sleep(e.timeout)
                continue
            except (BotBlocked, ChatNotFound, UserDeactivated) as e:
                logger.warning(f"Permanent error when sending photo to {chat_id}: {e}")
                return None
            except TelegramAPIError as e:
                if attempt < retry_count - 1:
                    current_delay = retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Failed to send photo (attempt {attempt + 1}/{retry_count}): {e}. Retrying in {current_delay}s")
                    await asyncio.sleep(current_delay)
                else:
                    logger.error(f"Failed to send photo after {retry_count} attempts: {e}")
                    return None

    except Exception as e:
        logger.error(f"Error in safe_send_photo: {e}")
        return None


# Keep other Telegram-specific utility functions
# These remain unchanged because they handle Telegram-specific features

async def safe_edit_message(
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        disable_web_page_preview: bool = False
) -> Optional[Message]:
    """Safely edit a message with error handling."""
    try:
        return await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview
        )
    except MessageNotModified:
        logger.debug("Message not modified (content is the same)")
        return None
    except TelegramAPIError as e:
        logger.error(f"Failed to edit message: {e}")
        return None


async def safe_answer_callback_query(
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
) -> bool:
    """Safely answer a callback query with error handling."""
    try:
        await bot.answer_callback_query(
            callback_query_id=callback_query_id,
            text=text,
            show_alert=show_alert
        )
        return True
    except InvalidQueryID:
        logger.warning("Invalid query ID (callback is too old)")
        return False
    except TelegramAPIError as e:
        logger.error(f"Failed to answer callback query: {e}")
        return False


async def delete_message_safe(
        chat_id: Union[int, str],
        message_id: int
) -> bool:
    """Safely delete a message with error handling."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except MessageToDeleteNotFound:
        logger.debug("Message to delete not found (already deleted)")
        return True
    except TelegramAPIError as e:
        logger.error(f"Failed to delete message: {e}")
        return False