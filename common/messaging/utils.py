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


def get_messenger_for_user(user_id: int) -> Tuple[Optional[str], Optional[str], Optional[Any]]:
    """
    Determine the messenger type and platform-specific ID for a user.

    Args:
        user_id: Database user ID

    Returns:
        Tuple of (platform_name, platform_id, messenger_instance)
    """
    from common.db.database import execute_query

    # Get user's messenger IDs from database
    sql = """
          SELECT telegram_id, viber_id, whatsapp_id
          FROM users
          WHERE id = %s
          """
    user = execute_query(sql, [user_id], fetchone=True)

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