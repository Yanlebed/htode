# services/telegram_service/app/utils/message_utils.py

import logging
import asyncio
from typing import Optional, Union, Dict, Any, List
from aiogram.types import InlineKeyboardMarkup, ParseMode, Message, CallbackQuery, InputMedia, InputFile
from aiogram.utils.exceptions import (
    MessageNotModified, BotBlocked, ChatNotFound,
    UserDeactivated, TelegramAPIError, RetryAfter,
    InvalidQueryID, MessageToDeleteNotFound
)
from ..bot import bot

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

    Args:
        chat_id: User or chat ID to send message to
        text: Message text
        parse_mode: Optional parse mode (Markdown or HTML)
        reply_markup: Optional reply markup (keyboard)
        disable_web_page_preview: Whether to disable web page preview
        retry_count: Number of retry attempts in case of network errors
        retry_delay: Initial delay between retries in seconds (increases exponentially)

    Returns:
        The sent Message object or None if all retries failed
    """
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

    # This should only happen if all retries fail without raising exceptions
    return None


async def safe_edit_message(
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        disable_web_page_preview: bool = False
) -> Optional[Message]:
    """
    Safely edit a message with error handling.

    Args:
        chat_id: User or chat ID where message is located
        message_id: ID of the message to edit
        text: New message text
        parse_mode: Optional parse mode (Markdown or HTML)
        reply_markup: Optional reply markup (keyboard)
        disable_web_page_preview: Whether to disable web page preview

    Returns:
        The edited Message object or None if editing failed
    """
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
        # This is not an error - the message was not modified because it's the same
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
    """
    Safely answer a callback query with error handling.

    Args:
        callback_query_id: Callback query ID to answer
        text: Optional text to show to the user
        show_alert: Whether to show as alert or notification

    Returns:
        True if successful, False otherwise
    """
    try:
        await bot.answer_callback_query(
            callback_query_id=callback_query_id,
            text=text,
            show_alert=show_alert
        )
        return True
    except InvalidQueryID:
        # This happens when the button press is too old
        logger.warning("Invalid query ID (callback is too old)")
        return False
    except TelegramAPIError as e:
        logger.error(f"Failed to answer callback query: {e}")
        return False


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

    Args:
        chat_id: User or chat ID to send photo to
        photo: Photo URL or InputFile
        caption: Optional photo caption
        parse_mode: Optional parse mode for caption
        reply_markup: Optional reply markup (keyboard)
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries in seconds

    Returns:
        The sent Message object or None if all retries failed
    """
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
            # Respect Telegram's rate limiting
            logger.warning(f"Rate limit exceeded. Retrying in {e.timeout} seconds.")
            await asyncio.sleep(e.timeout)
            # Don't count this as an attempt since it's just rate limiting
            continue
        except (BotBlocked, ChatNotFound, UserDeactivated) as e:
            # These are permanent errors, no need to retry
            logger.warning(f"Permanent error when sending photo to {chat_id}: {e}")
            return None
        except TelegramAPIError as e:
            # For other Telegram API errors, we'll retry with backoff
            if attempt < retry_count - 1:
                # Exponential backoff
                current_delay = retry_delay * (2 ** attempt)
                logger.warning(
                    f"Failed to send photo (attempt {attempt + 1}/{retry_count}): {e}. Retrying in {current_delay}s")
                await asyncio.sleep(current_delay)
            else:
                logger.error(f"Failed to send photo after {retry_count} attempts: {e}")
                return None

    # This should only happen if all retries fail without raising exceptions
    return None


async def delete_message_safe(
        chat_id: Union[int, str],
        message_id: int
) -> bool:
    """
    Safely delete a message with error handling.

    Args:
        chat_id: User or chat ID where message is located
        message_id: ID of the message to delete

    Returns:
        True if successful or message already deleted, False otherwise
    """
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except MessageToDeleteNotFound:
        # Message already deleted - not an error
        logger.debug("Message to delete not found (already deleted)")
        return True
    except TelegramAPIError as e:
        logger.error(f"Failed to delete message: {e}")
        return False
