# common/messaging/utils.py

import logging
import asyncio
import functools
import random
from typing import Callable, List, Type, Dict, Any, Optional, TypeVar, Tuple, Union

from .platform_utils import format_user_id_for_platform, resolve_user_id, get_messenger_instance

logger = logging.getLogger(__name__)

# Type variable for return value
T = TypeVar('T')


class MessageFormatter:
    """
    Utility class for formatting messages based on platform.
    Provides consistent formatting across different messaging platforms.
    """

    @staticmethod
    def format_ad_text(ad_data: Dict[str, Any], platform: str = "default") -> str:
        """
        Format ad text based on platform-specific requirements.

        Args:
            ad_data: Dictionary with ad information
            platform: Target platform (telegram, viber, whatsapp)

        Returns:
            Formatted ad text string
        """
        from common.config import GEO_ID_MAPPING

        # Extract ad data with defaults
        city_id = ad_data.get('city')
        city_name = GEO_ID_MAPPING.get(city_id, "Невідомо")
        price = ad_data.get('price', 0)
        address = ad_data.get('address', "Невідомо")
        rooms_count = ad_data.get('rooms_count', "Невідомо")
        square_feet = ad_data.get('square_feet', "Невідомо")
        floor = ad_data.get('floor', "Невідомо")
        total_floors = ad_data.get('total_floors', "Невідомо")

        # Apply platform-specific formatting
        if platform == "telegram":
            # Telegram supports markdown
            text = (
                f"💰 Ціна: *{int(price)}* грн.\n"
                f"🏙️ Місто: *{city_name}*\n"
                f"📍 Адреса: *{address}*\n"
                f"🛏️ Кіл-сть кімнат: *{rooms_count}*\n"
                f"📐 Площа: *{square_feet}* кв.м.\n"
                f"🏢 Поверх: *{floor}* з *{total_floors}*\n"
            )
        elif platform in ["viber", "whatsapp"]:
            # Standard text formatting for platforms without markdown
            text = (
                f"💰 Ціна: {int(price)} грн.\n"
                f"🏙️ Місто: {city_name}\n"
                f"📍 Адреса: {address}\n"
                f"🛏️ Кіл-сть кімнат: {rooms_count}\n"
                f"📐 Площа: {square_feet} кв.м.\n"
                f"🏢 Поверх: {floor} з {total_floors}\n"
            )
        else:
            # Default format for unknown platforms
            text = (
                f"💰 Ціна: {int(price)} грн.\n"
                f"🏙️ Місто: {city_name}\n"
                f"📍 Адреса: {address}\n"
                f"🛏️ Кіл-сть кімнат: {rooms_count}\n"
                f"📐 Площа: {square_feet} кв.м.\n"
                f"🏢 Поверх: {floor} з {total_floors}\n"
            )

        return text


# --- New Consolidated Messaging Functions ---

async def get_messenger_for_user(user_id: Union[int, str]) -> Tuple[Optional[str], Optional[str], Optional[Any]]:
    """
    Determine the messenger type and platform-specific ID for a user.
    Can handle either database user ID or platform-specific ID.

    Args:
        user_id: Database user ID or platform-specific ID

    Returns:
        Tuple of (platform_name, platform_id, messenger_instance)
    """
    db_user_id, platform_name, platform_id = resolve_user_id(user_id)

    if platform_name and platform_id:
        messenger = get_messenger_instance(platform_name)
        return platform_name, platform_id, messenger

    return None, None, None


async def safe_send_message(
        user_id: Union[str, int],
        text: str,
        platform: Optional[str] = None,
        retry_count: int = 3,
        retry_delay: int = 1,
        **kwargs
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a text message across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        text: Message text
        platform: Optional platform override ("telegram", "viber", "whatsapp")
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries
        **kwargs: Platform-specific parameters (parse_mode, reply_markup, keyboard, etc.)

    Returns:
        Response from the messaging platform or boolean success status
    """
    from common.messaging.service import messaging_service

    try:
        # Get database user ID, platform and messenger
        db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)

        # If we have a database user ID, try to use the unified messaging service
        if db_user_id:
            try:
                success = await messaging_service.send_notification(
                    user_id=db_user_id,
                    text=text,
                    **kwargs
                )
                if success:
                    return True
            except Exception as e:
                logger.warning(f"Error using messaging service: {e}, falling back to direct send")

        # If we have platform info, try direct send
        if platform_name and platform_id:
            messenger = get_messenger_instance(platform_name)
            if messenger:
                # Format user ID for this platform
                formatted_id = format_user_id_for_platform(platform_id, platform_name)

                # Send the message with retry logic
                for attempt in range(retry_count):
                    try:
                        return await messenger.send_text(formatted_id, text, **kwargs)
                    except Exception as e:
                        if attempt < retry_count - 1:
                            current_delay = retry_delay * (2 ** attempt)
                            logger.warning(
                                f"Failed to send message (attempt {attempt + 1}/{retry_count}): {e}. "
                                f"Retrying in {current_delay}s"
                            )
                            await asyncio.sleep(current_delay)
                        else:
                            logger.error(f"Failed to send message after {retry_count} attempts: {e}")
                            return None

        logger.error(f"Could not send message - unable to resolve user ID or platform: {user_id}")
        return None
    except Exception as e:
        logger.error(f"Error in unified safe_send_message: {e}")
        return None


async def safe_send_media(
        user_id: Union[str, int],
        media_url: str,
        caption: Optional[str] = None,
        platform: Optional[str] = None,
        retry_count: int = 3,
        retry_delay: int = 1,
        **kwargs
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a media message across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        media_url: URL of the media to send
        caption: Optional caption text
        platform: Optional platform override ("telegram", "viber", "whatsapp")
        retry_count: Number of retry attempts
        retry_delay: Initial delay between retries
        **kwargs: Platform-specific parameters (parse_mode, reply_markup, keyboard, etc.)

    Returns:
        Response from the messaging platform or boolean success status
    """
    from common.messaging.service import messaging_service

    try:
        # Get database user ID, platform and messenger
        db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)

        # If we have a database user ID, try to use the unified messaging service
        if db_user_id:
            try:
                success = await messaging_service.send_notification(
                    user_id=db_user_id,
                    text=caption,
                    image_url=media_url,
                    **kwargs
                )
                if success:
                    return True
            except Exception as e:
                logger.warning(f"Error using messaging service: {e}, falling back to direct send")

        # If we have platform info, try direct send
        if platform_name and platform_id:
            messenger = get_messenger_instance(platform_name)
            if messenger:
                # Format user ID for this platform
                formatted_id = format_user_id_for_platform(platform_id, platform_name)

                # Send the media with retry logic
                for attempt in range(retry_count):
                    try:
                        return await messenger.send_media(formatted_id, media_url, caption=caption, **kwargs)
                    except Exception as e:
                        if attempt < retry_count - 1:
                            current_delay = retry_delay * (2 ** attempt)
                            logger.warning(
                                f"Failed to send media (attempt {attempt + 1}/{retry_count}): {e}. "
                                f"Retrying in {current_delay}s"
                            )
                            await asyncio.sleep(current_delay)
                        else:
                            logger.error(f"Failed to send media after {retry_count} attempts: {e}")
                            # Try sending just text if media fails
                            if caption:
                                try:
                                    return await safe_send_message(
                                        user_id=user_id,
                                        text=f"{caption}\n\n[Media URL: {media_url}]",
                                        platform=platform_name,
                                        **kwargs
                                    )
                                except Exception:
                                    pass
                            return None

        logger.error(f"Could not send media - unable to resolve user ID or platform: {user_id}")
        return None
    except Exception as e:
        logger.error(f"Error in unified safe_send_media: {e}")
        return None


async def safe_send_menu(
        user_id: Union[str, int],
        text: str,
        options: List[Dict[str, str]],
        platform: Optional[str] = None,
        **kwargs
) -> Union[Any, bool, None]:
    """
    Unified function to safely send a menu across any platform.

    Args:
        user_id: Platform-specific user ID or database user ID
        text: Menu title/description text
        options: List of option dictionaries with at least 'text' and 'value' keys
        platform: Optional platform override ("telegram", "viber", "whatsapp")
        **kwargs: Platform-specific parameters

    Returns:
        Response from the messaging platform or boolean success status
    """
    try:
        # Get database user ID, platform and messenger
        db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)

        # If we have platform info, send the menu
        if platform_name and platform_id:
            messenger = get_messenger_instance(platform_name)
            if messenger:
                # Format user ID for this platform
                formatted_id = format_user_id_for_platform(platform_id, platform_name)

                # Send the menu
                return await messenger.send_menu(formatted_id, text, options, **kwargs)

        logger.error(f"Could not send menu - unable to resolve user ID or platform: {user_id}")
        return None
    except Exception as e:
        logger.error(f"Error in unified safe_send_menu: {e}")
        return None


# Telegram-specific helper functions that don't fit into the unified pattern

async def safe_edit_message_telegram(
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Any = None,
        disable_web_page_preview: bool = False
) -> Optional[Any]:
    """
    Telegram-specific function to safely edit a message.

    Args:
        chat_id: Telegram chat ID
        message_id: Message ID to edit
        text: New message text
        parse_mode: Optional parse mode (Markdown or HTML)
        reply_markup: Optional reply markup (keyboard)
        disable_web_page_preview: Whether to disable web page preview

    Returns:
        Response from Telegram or None if failed
    """
    from services.telegram_service.app.bot import bot
    from aiogram.utils.exceptions import MessageNotModified, TelegramAPIError

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


async def safe_answer_callback_query_telegram(
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
) -> bool:
    """
    Telegram-specific function to safely answer a callback query.

    Args:
        callback_query_id: Callback query ID
        text: Optional text to show to the user
        show_alert: Whether to show as alert (vs. toast)

    Returns:
        True if succeeded, False otherwise
    """
    from services.telegram_service.app.bot import bot
    from aiogram.utils.exceptions import InvalidQueryID, TelegramAPIError

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


async def delete_message_safe_telegram(
        chat_id: Union[int, str],
        message_id: int
) -> bool:
    """
    Telegram-specific function to safely delete a message.

    Args:
        chat_id: Telegram chat ID
        message_id: Message ID to delete

    Returns:
        True if succeeded or already deleted, False otherwise
    """
    from services.telegram_service.app.bot import bot
    from aiogram.utils.exceptions import MessageToDeleteNotFound, TelegramAPIError

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except MessageToDeleteNotFound:
        logger.debug("Message to delete not found (already deleted)")
        return True
    except TelegramAPIError as e:
        logger.error(f"Failed to delete message: {e}")
        return False