# common/messaging/unified_platform_utils.py

import logging
import asyncio
import random
from typing import Dict, Any, Optional, Tuple, Union, List, Type, Callable, TypeVar

logger = logging.getLogger(__name__)

# Type variable for return value
T = TypeVar('T')

# ===== Platform Detection and Resolution =====

def detect_platform_from_id(user_id: str) -> Tuple[str, str]:
    """
    Detect messaging platform from user ID format.

    Args:
        user_id: Platform-specific user ID

    Returns:
        Tuple of (platform_name, clean_user_id)
    """
    user_id_str = str(user_id)

    if user_id_str.startswith("whatsapp:"):
        return "whatsapp", user_id_str
    elif len(user_id_str) > 20:  # Viber IDs are typically long UUIDs
        return "viber", user_id_str
    else:
        # Default to Telegram for numeric IDs and other formats
        return "telegram", user_id_str


def format_user_id_for_platform(user_id: str, platform: str) -> str:
    """
    Format a user ID according to platform requirements.
    Centralized implementation to avoid duplication.

    Args:
        user_id: Raw user identifier
        platform: Target platform (telegram, viber, whatsapp)

    Returns:
        Formatted user identifier
    """
    if platform == "whatsapp" and not user_id.startswith("whatsapp:"):
        return f"whatsapp:{user_id}"

    # Other platforms don't need special formatting
    return user_id


def resolve_user_id(user_id: Union[int, str], platform: Optional[str] = None) -> Tuple[
    Optional[int], Optional[str], Optional[str]]:
    """
    Resolve a user ID to get database ID and platform information.

    Args:
        user_id: Either a database user ID or platform-specific ID
        platform: Optional platform hint

    Returns:
        Tuple of (database_user_id, platform_name, platform_id)
    """
    from common.db.models import get_db_user_id_by_telegram_id, get_platform_ids_for_user

    # Case 1: Database user ID
    if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
        db_user_id = int(user_id)

        # Get platform IDs for this user
        platform_ids = get_platform_ids_for_user(db_user_id)

        # Determine which platform to use (priority order)
        if platform_ids.get("telegram_id"):
            return db_user_id, "telegram", str(platform_ids["telegram_id"])
        elif platform_ids.get("viber_id"):
            return db_user_id, "viber", platform_ids["viber_id"]
        elif platform_ids.get("whatsapp_id"):
            return db_user_id, "whatsapp", platform_ids["whatsapp_id"]
        else:
            return db_user_id, None, None

    # Case 2: Platform-specific ID

    # If platform is provided, use it
    if platform:
        platform_name = platform
        platform_id = user_id
    else:
        # Detect platform from ID format
        platform_name, platform_id = detect_platform_from_id(user_id)

    # Get database user ID
    db_user_id = get_db_user_id_by_telegram_id(platform_id, messenger_type=platform_name)

    return db_user_id, platform_name, platform_id


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


def get_messenger_instance(platform: str):
    """
    Get the appropriate messenger instance for a platform.

    Args:
        platform: Platform name (telegram, viber, whatsapp)

    Returns:
        Messenger instance or None if not found
    """
    try:
        if platform == "telegram":
            from common.messaging.telegram_messaging import TelegramMessaging
            from services.telegram_service.app.bot import bot
            return TelegramMessaging(bot)
        elif platform == "viber":
            from common.messaging.viber_messaging import ViberMessaging
            from services.viber_service.app.bot import viber
            return ViberMessaging(viber)
        elif platform == "whatsapp":
            from common.messaging.whatsapp_messaging import WhatsAppMessaging
            from services.whatsapp_service.app.bot import client
            return WhatsAppMessaging(client)
        else:
            logger.warning(f"Unknown platform: {platform}")
            return None
    except ImportError as e:
        logger.error(f"Error importing messenger for {platform}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting messenger instance for {platform}: {e}")
        return None


# ===== Messaging Utilities =====

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


# ===== Unified Message Sending Functions =====

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
                            jitter = random.uniform(0.8, 1.2)
                            final_delay = current_delay * jitter
                            logger.warning(
                                f"Failed to send message (attempt {attempt + 1}/{retry_count}): {e}. "
                                f"Retrying in {final_delay:.2f}s"
                            )
                            await asyncio.sleep(final_delay)
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
                            jitter = random.uniform(0.8, 1.2)
                            final_delay = current_delay * jitter
                            logger.warning(
                                f"Failed to send media (attempt {attempt + 1}/{retry_count}): {e}. "
                                f"Retrying in {final_delay:.2f}s"
                            )
                            await asyncio.sleep(final_delay)
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


# ===== Platform-Specific Helper Functions =====

# Telegram-specific helpers

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
    try:
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
    except ImportError as e:
        logger.error(f"Telegram dependencies not available: {e}")
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
    try:
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
    except ImportError as e:
        logger.error(f"Telegram dependencies not available: {e}")
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
    try:
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
    except ImportError as e:
        logger.error(f"Telegram dependencies not available: {e}")
        return False