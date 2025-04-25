# common/messaging/platform_utils.py

import logging
from typing import Tuple, Optional, Union, Dict, Any

logger = logging.getLogger(__name__)


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
    Format a user ID for a specific platform.

    Args:
        user_id: Raw user identifier
        platform: Platform name (telegram, viber, whatsapp)

    Returns:
        Properly formatted user ID for the platform
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