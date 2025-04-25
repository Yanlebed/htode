# common/messaging/service.py

import logging
from typing import Dict, Any, Optional, List, Union

from .interface import MessagingInterface
from .utils import get_messenger_for_user

logger = logging.getLogger(__name__)


class MessagingService:
    """
    Unified messaging service for sending messages across different platforms.
    Uses a plugin architecture with platform-specific adapters.
    """

    def __init__(self):
        """Initialize the messaging service without any messengers."""
        self._messengers = {}

    def register_messenger(self, platform: str, messenger: MessagingInterface) -> None:
        """
        Register a messenger implementation for a specific platform.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            messenger: Messenger implementation for that platform
        """
        self._messengers[platform] = messenger
        logger.info(f"Registered messenger for platform: {platform}")

    def get_messenger(self, platform: str) -> Optional[MessagingInterface]:
        """
        Get the messenger for a specific platform.

        Args:
            platform: Platform identifier

        Returns:
            Messenger instance or None if not registered
        """
        return self._messengers.get(platform)

    async def get_user_platform(self, user_id: int) -> tuple[Optional[str], Optional[str]]:
        """
        Determine which platform a user is on and get their platform-specific ID.

        Args:
            user_id: Database user ID

        Returns:
            Tuple of (platform_name, platform_specific_id) or (None, None)
        """
        from common.db.database import execute_query

        sql = """
              SELECT telegram_id, viber_id, whatsapp_id
              FROM users
              WHERE id = %s
              """
        user = execute_query(sql, [user_id], fetchone=True)

        if not user:
            return None, None

        # Check each platform ID
        if user.get("telegram_id"):
            return "telegram", str(user["telegram_id"])

        if user.get("viber_id"):
            return "viber", user["viber_id"]

        if user.get("whatsapp_id"):
            return "whatsapp", user["whatsapp_id"]

        return None, None

    async def send_notification(
            self,
            user_id: int,
            text: str,
            image_url: Optional[str] = None,
            options: Optional[List[Dict[str, str]]] = None,
            **kwargs
    ) -> bool:
        """
        Send a notification to a user using their preferred messenger.

        Args:
            user_id: Database user ID
            text: Message text
            image_url: Optional image URL
            options: Optional list of menu options
            **kwargs: Additional platform-specific parameters

        Returns:
            True if sent successfully, False otherwise
        """
        platform, platform_id = await self.get_user_platform(user_id)

        if not platform or not platform_id:
            logger.warning(f"No messaging platform found for user {user_id}")
            return False

        messenger = self.get_messenger(platform)
        if not messenger:
            logger.error(f"No messenger implementation registered for platform {platform}")
            return False

        try:
            # Format the user ID for the specific platform
            formatted_id = await messenger.format_user_id(platform_id)

            if options:
                # Send as a menu
                await messenger.send_menu(formatted_id, text, options, **kwargs)
            elif image_url:
                # Send as media with caption
                await messenger.send_media(formatted_id, image_url, caption=text, **kwargs)
            else:
                # Send as plain text
                await messenger.send_text(formatted_id, text, **kwargs)

            return True
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id} via {platform}: {e}")
            return False

    async def send_ad(
            self,
            user_id: int,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> bool:
        """
        Send an ad to a user using their preferred messenger.

        Args:
            user_id: Database user ID
            ad_data: Dictionary with ad information
            image_url: Optional primary image URL
            **kwargs: Additional platform-specific parameters

        Returns:
            True if sent successfully, False otherwise
        """
        platform, platform_id = await self.get_user_platform(user_id)

        if not platform or not platform_id:
            logger.warning(f"No messaging platform found for user {user_id}")
            return False

        messenger = self.get_messenger(platform)
        if not messenger:
            logger.error(f"No messenger implementation registered for platform {platform}")
            return False

        try:
            # Format the user ID for the specific platform
            formatted_id = await messenger.format_user_id(platform_id)

            # Send the ad using platform-specific formatting
            await messenger.send_ad(formatted_id, ad_data, image_url, **kwargs)
            return True
        except Exception as e:
            logger.error(f"Error sending ad to user {user_id} via {platform}: {e}")
            return False

    @classmethod
    def create_default(cls) -> 'MessagingService':
        """
        Create a messaging service with all available messengers registered.

        Returns:
            Configured MessagingService instance
        """
        # Import messenger implementations
        from .telegram_messaging import TelegramMessaging
        from .viber_messaging import ViberMessaging
        from .whatsapp_messaging import WhatsAppMessaging

        # Import bot instances
        from services.telegram_service.app.bot import bot as telegram_bot
        from services.viber_service.app.bot import viber as viber_bot
        from services.whatsapp_service.app.bot import client as twilio_client

        # Create and configure service
        service = cls()
        service.register_messenger("telegram", TelegramMessaging(telegram_bot))
        service.register_messenger("viber", ViberMessaging(viber_bot))
        service.register_messenger("whatsapp", WhatsAppMessaging(twilio_client))

        return service


# Create a singleton instance for global use
messaging_service = MessagingService.create_default()