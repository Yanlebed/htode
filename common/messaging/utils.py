# common/messaging/utils.py

import logging
import asyncio
import functools
import random
from typing import Callable, List, Type, Dict, Any, Optional, TypeVar, Tuple, Union

logger = logging.getLogger(__name__)

# Type variable for return value
T = TypeVar('T')


def retry_with_exponential_backoff(
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        retryable_exceptions: List[Type[Exception]] = None
):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        retryable_exceptions: List of exception types to retry on (defaults to all)

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if retryable_exceptions is None:
                retry_on = (Exception,)
            else:
                retry_on = tuple(retryable_exceptions)

            last_exception = None

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        # Calculate exponential delay with jitter
                        delay = initial_delay * (backoff_factor ** attempt)
                        jitter = random.uniform(0.8, 1.2)
                        final_delay = delay * jitter

                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {final_delay:.2f}s"
                        )
                        await asyncio.sleep(final_delay)
                    else:
                        logger.error(f"All {max_retries} retry attempts failed. Last error: {e}")
                        raise
                except Exception as e:
                    # Don't retry on non-retryable exceptions
                    logger.error(f"Non-retryable exception occurred: {e}")
                    raise

            # This will only be reached if max_retries is 0
            if last_exception:
                raise last_exception
            return None

        return wrapper

    return decorator


def detect_platform_from_id(user_id: str) -> Tuple[Optional[str], str]:
    """
    Detect messaging platform from user ID format.

    Args:
        user_id: Platform-specific user ID

    Returns:
        Tuple of (platform_name, user_id)
    """
    user_id_str = str(user_id)

    if user_id_str.startswith("whatsapp:"):
        return "whatsapp", user_id_str
    elif len(user_id_str) > 20:  # Viber IDs are typically long UUIDs
        return "viber", user_id_str
    else:
        # Default to Telegram for numeric IDs
        return "telegram", user_id_str


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
    from common.messaging.service import messaging_service
    from common.db.database import execute_query

    # Check if this is a database ID
    if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
        # Get user's messenger IDs from database
        sql = """
              SELECT id, telegram_id, viber_id, whatsapp_id
              FROM users
              WHERE id = %s
              """
        user = execute_query(sql, [int(user_id)], fetchone=True)

        if not user:
            logger.warning(f"User with ID {user_id} not found in database")
            return None, None, None

        # Try each platform in order of preference
        if user.get("telegram_id"):
            from .telegram_messaging import TelegramMessaging
            from services.telegram_service.app.bot import bot
            return "telegram", str(user["telegram_id"]), TelegramMessaging(bot)

        if user.get("viber_id"):
            from .viber_messaging import ViberMessaging
            from services.viber_service.app.bot import viber
            return "viber", user["viber_id"], ViberMessaging(viber)

        if user.get("whatsapp_id"):
            from .whatsapp_messaging import WhatsAppMessaging
            from services.whatsapp_service.app.bot import client
            return "whatsapp", user["whatsapp_id"], WhatsAppMessaging(client)

        return None, None, None
    else:
        # This is a platform-specific ID, detect which platform
        platform, platform_id = detect_platform_from_id(user_id)

        if platform == "telegram":
            from .telegram_messaging import TelegramMessaging
            from services.telegram_service.app.bot import bot
            return platform, platform_id, TelegramMessaging(bot)
        elif platform == "viber":
            from .viber_messaging import ViberMessaging
            from services.viber_service.app.bot import viber
            return platform, platform_id, ViberMessaging(viber)
        elif platform == "whatsapp":
            from .whatsapp_messaging import WhatsAppMessaging
            from services.whatsapp_service.app.bot import client
            return platform, platform_id, WhatsAppMessaging(client)

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
    from common.db.models import get_db_user_id_by_telegram_id

    try:
        # First try to use the unified messaging service with database user ID
        if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
            # This is likely a database user ID
            db_user_id = int(user_id)
            success = await messaging_service.send_notification(
                user_id=db_user_id,
                text=text,
                **kwargs
            )
            return success

        # If we get here, we have a platform-specific ID

        # If platform is explicitly specified, use it
        if platform:
            platform_name = platform
            platform_id = user_id
        else:
            # Try to determine platform from ID format
            platform_name, platform_id = detect_platform_from_id(user_id)

        # Try to get database user ID for this platform-specific ID
        messenger_type = platform_name if platform_name else "telegram"  # Default to telegram
        db_user_id = get_db_user_id_by_telegram_id(platform_id, messenger_type=messenger_type)

        if db_user_id:
            # We have a database user ID, use the unified service
            success = await messaging_service.send_notification(
                user_id=db_user_id,
                text=text,
                **kwargs
            )
            if success:
                return True

        # If we get here, either we couldn't get a database user ID or the unified service failed
        # Fall back to platform-specific implementation

        # Get the appropriate messenger for this platform
        _, _, messenger = await get_messenger_for_user(platform_id if platform_name else user_id)

        if not messenger:
            logger.error(f"Could not determine appropriate messenger for user ID {user_id}")
            return False

        # Format user ID for this platform
        formatted_id = await messenger.format_user_id(platform_id if platform_name else user_id)

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
    from common.db.models import get_db_user_id_by_telegram_id

    try:
        # First try to use the unified messaging service with database user ID
        if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
            # This is likely a database user ID
            db_user_id = int(user_id)
            success = await messaging_service.send_notification(
                user_id=db_user_id,
                text=caption,
                image_url=media_url,
                **kwargs
            )
            return success

        # If we get here, we have a platform-specific ID

        # If platform is explicitly specified, use it
        if platform:
            platform_name = platform
            platform_id = user_id
        else:
            # Try to determine platform from ID format
            platform_name, platform_id = detect_platform_from_id(user_id)

        # Try to get database user ID for this platform-specific ID
        messenger_type = platform_name if platform_name else "telegram"  # Default to telegram
        db_user_id = get_db_user_id_by_telegram_id(platform_id, messenger_type=messenger_type)

        if db_user_id:
            # We have a database user ID, use the unified service
            success = await messaging_service.send_notification(
                user_id=db_user_id,
                text=caption,
                image_url=media_url,
                **kwargs
            )
            if success:
                return True

        # If we get here, either we couldn't get a database user ID or the unified service failed
        # Fall back to platform-specific implementation

        # Get the appropriate messenger for this platform
        _, _, messenger = await get_messenger_for_user(platform_id if platform_name else user_id)

        if not messenger:
            logger.error(f"Could not determine appropriate messenger for user ID {user_id}")
            return False

        # Format user ID for this platform
        formatted_id = await messenger.format_user_id(platform_id if platform_name else user_id)

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
                                platform=platform,
                                **kwargs
                            )
                        except Exception:
                            pass
                    return None

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
    from common.messaging.service import messaging_service

    try:
        # First try to use the unified messaging service with database user ID
        if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
            # This is likely a database user ID
            platform_name, platform_id, messenger = await get_messenger_for_user(int(user_id))

            if messenger:
                return await messenger.send_menu(
                    user_id=platform_id,
                    text=text,
                    options=options,
                    **kwargs
                )
            return False

        # If we get here, we have a platform-specific ID

        # If platform is explicitly specified, use it
        if platform:
            platform_name = platform
            platform_id = user_id
        else:
            # Try to determine platform from ID format
            platform_name, platform_id = detect_platform_from_id(user_id)

        # Get the appropriate messenger for this platform
        _, _, messenger = await get_messenger_for_user(platform_id if platform_name else user_id)

        if not messenger:
            logger.error(f"Could not determine appropriate messenger for user ID {user_id}")
            return False

        # Format user ID for this platform
        formatted_id = await messenger.format_user_id(platform_id if platform_name else user_id)

        # Send the menu
        return await messenger.send_menu(formatted_id, text, options, **kwargs)

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