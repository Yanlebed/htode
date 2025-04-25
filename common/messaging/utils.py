# common/messaging/utils.py

import logging
import asyncio
import functools
from typing import Callable, List, Any, Type, Dict, Optional, TypeVar, Union, Tuple

logger = logging.getLogger(__name__)

# Type variable for return value
T = TypeVar('T')


def retry_with_exponential_backoff(
        retryable_exceptions: List[Type[Exception]] = None,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0
):
    """
    Decorator for retrying asynchronous functions with exponential backoff.

    Args:
        retryable_exceptions: List of exception types to retry on (default: retry on all exceptions)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry attempt

    Returns:
        Decorator function
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            nonlocal retryable_exceptions

            if retryable_exceptions is None:
                retryable_exceptions = [Exception]

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except tuple(retryable_exceptions) as e:
                    if attempt < max_retries - 1:
                        # Calculate exponential delay with jitter
                        delay = initial_delay * (backoff_factor ** attempt)
                        # Add a small random jitter to avoid thundering herd problem
                        import random
                        jitter = random.uniform(0.8, 1.2)
                        delay = delay * jitter

                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {delay:.2f}s"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"All {max_retries} retry attempts failed")
                        raise
                except Exception as e:
                    # Don't retry on non-retryable exceptions
                    logger.error(f"Non-retryable exception: {e}")
                    raise

            # This should never be reached due to the raise in the loop
            return None  # For type checking only

        return wrapper

    return decorator


class MessageRenderer:
    """Utility class for rendering messages across different platforms"""

    @staticmethod
    def render_ad_text(ad_data: Dict[str, Any], platform: str = None) -> str:
        """
        Generate text for an ad listing with optional platform-specific formatting.

        Args:
            ad_data: Dictionary containing ad data
            platform: Optional platform identifier for customized formatting

        Returns:
            Formatted ad text
        """
        from common.config import GEO_ID_MAPPING

        # Get required fields with fallbacks
        city_id = ad_data.get('city')
        city_name = GEO_ID_MAPPING.get(city_id, "Невідомо")
        price = ad_data.get('price', 0)
        address = ad_data.get('address', "Невідомо")
        rooms_count = ad_data.get('rooms_count', "Невідомо")
        square_feet = ad_data.get('square_feet', "Невідомо")
        floor = ad_data.get('floor', "Невідомо")
        total_floors = ad_data.get('total_floors', "Невідомо")

        # Format differently based on platform
        if platform == "telegram":
            # Telegram supports Markdown
            text = (
                f"💰 Ціна: *{int(price)}* грн.\n"
                f"🏙️ Місто: *{city_name}*\n"
                f"📍 Адреса: *{address}*\n"
                f"🛏️ Кіл-сть кімнат: *{rooms_count}*\n"
                f"📐 Площа: *{square_feet}* кв.м.\n"
                f"🏢 Поверх: *{floor}* з *{total_floors}*\n"
            )
        elif platform == "viber":
            # Viber has limited formatting capabilities
            text = (
                f"💰 Ціна: {int(price)} грн.\n"
                f"🏙️ Місто: {city_name}\n"
                f"📍 Адреса: {address}\n"
                f"🛏️ Кіл-сть кімнат: {rooms_count}\n"
                f"📐 Площа: {square_feet} кв.м.\n"
                f"🏢 Поверх: {floor} з {total_floors}\n"
            )
        elif platform == "whatsapp":
            # WhatsApp supports plain text with emoji
            text = (
                f"💰 Ціна: {int(price)} грн.\n"
                f"🏙️ Місто: {city_name}\n"
                f"📍 Адреса: {address}\n"
                f"🛏️ Кіл-сть кімнат: {rooms_count}\n"
                f"📐 Площа: {square_feet} кв.м.\n"
                f"🏢 Поверх: {floor} з {total_floors}\n"
            )
        else:
            # Default formatting
            text = (
                f"💰 Ціна: {int(price)} грн.\n"
                f"🏙️ Місто: {city_name}\n"
                f"📍 Адреса: {address}\n"
                f"🛏️ Кіл-сть кімнат: {rooms_count}\n"
                f"📐 Площа: {square_feet} кв.м.\n"
                f"🏢 Поверх: {floor} з {total_floors}\n"
            )

        return text

    @staticmethod
    def create_ad_buttons(
            platform: str,
            ad_id: int,
            resource_url: str,
            images: Optional[List[str]] = None,
            phones: Optional[List[str]] = None
    ) -> Any:
        """
        Create platform-specific buttons/actions for an ad.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            ad_id: Ad database ID
            resource_url: Ad source URL
            images: Optional list of image URLs
            phones: Optional list of phone numbers

        Returns:
            Platform-specific buttons object or None
        """
        if platform == "telegram":
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

            markup = InlineKeyboardMarkup(row_width=2)

            # Add gallery button if images are available
            if images and len(images) > 0:
                image_str = ",".join(images)
                gallery_url = f"https://example.com/gallery?images={image_str}"
                markup.add(InlineKeyboardButton(
                    text="🖼 Більше фото",
                    web_app=WebAppInfo(url=gallery_url)
                ))

            # Add phone button if phones are available
            if phones and len(phones) > 0:
                phone_str = ",".join(phones)
                phone_webapp_url = f"https://example.com/phones?numbers={phone_str}"
                markup.add(InlineKeyboardButton(
                    text="📲 Подзвонити",
                    web_app=WebAppInfo(url=phone_webapp_url)
                ))

            # Add favorite and full description buttons
            markup.add(
                InlineKeyboardButton("❤️ Додати в обрані", callback_data=f"add_fav:{ad_id}"),
                InlineKeyboardButton("ℹ️ Повний опис", callback_data=f"show_more:{resource_url}")
            )

            return markup

        elif platform == "viber":
            keyboard = {
                "Type": "keyboard",
                "Buttons": [
                    {
                        "Columns": 3,
                        "Rows": 1,
                        "Text": "🖼 Більше фото",
                        "ActionType": "reply",
                        "ActionBody": f"more_photos:{ad_id}"
                    },
                    {
                        "Columns": 3,
                        "Rows": 1,
                        "Text": "📲 Подзвонити",
                        "ActionType": "reply",
                        "ActionBody": f"call_contact:{ad_id}"
                    },
                    {
                        "Columns": 3,
                        "Rows": 1,
                        "Text": "❤️ Додати в обрані",
                        "ActionType": "reply",
                        "ActionBody": f"add_fav:{ad_id}"
                    },
                    {
                        "Columns": 3,
                        "Rows": 1,
                        "Text": "ℹ️ Повний опис",
                        "ActionType": "reply",
                        "ActionBody": f"show_more:{resource_url}"
                    }
                ]
            }

            return keyboard

        elif platform == "whatsapp":
            # WhatsApp doesn't support buttons, so we return instructions as text
            instructions = (
                "\n\nДоступні дії:\n"
                f"- Відповідь 'фото {ad_id}' для більше фото\n"
                f"- Відповідь 'тел {ad_id}' для номерів телефону\n"
                f"- Відповідь 'обр {ad_id}' щоб додати в обрані\n"
                f"- Відповідь 'опис {ad_id}' для повного опису"
            )

            return instructions

        else:
            return None


class MessengerFactory:
    """Factory for creating messenger instances for different platforms"""

    @staticmethod
    def create_messenger(platform: str) -> Optional['AbstractMessenger']:
        """
        Create a messenger instance for the specified platform.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)

        Returns:
            AbstractMessenger implementation for the platform or None if not supported
        """
        if platform == "telegram":
            from .plugins.telegram import TelegramMessenger
            from services.telegram_service.app.bot import bot
            return TelegramMessenger(bot)

        elif platform == "viber":
            from .plugins.viber import ViberMessenger
            from services.viber_service.app.bot import viber
            return ViberMessenger(viber)

        elif platform == "whatsapp":
            from .plugins.whatsapp import WhatsAppMessenger
            from services.whatsapp_service.app.bot import client
            return WhatsAppMessenger(client)

        else:
            logger.error(f"Unsupported platform: {platform}")
            return None


def get_messenger_for_user(user_id: int) -> Tuple[Optional[str], Optional[str], Optional['AbstractMessenger']]:
    """
    Get messenger type, messenger-specific ID, and messenger instance for a user.

    Args:
        user_id: Database user ID

    Returns:
        Tuple of (messenger_type, messenger_id, messenger_instance) or (None, None, None) if not found
    """
    from common.db.database import execute_query

    sql = """
          SELECT telegram_id, viber_id, whatsapp_id
          FROM users
          WHERE id = %s
          """
    user = execute_query(sql, [user_id], fetchone=True)

    if not user:
        return None, None, None

    # Check each platform in order of preference
    if user.get("telegram_id"):
        return "telegram", str(user["telegram_id"]), MessengerFactory.create_messenger("telegram")

    if user.get("viber_id"):
        return "viber", user["viber_id"], MessengerFactory.create_messenger("viber")

    if user.get("whatsapp_id"):
        return "whatsapp", user["whatsapp_id"], MessengerFactory.create_messenger("whatsapp")

    return None, None, None