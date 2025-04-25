# common/messaging/service.py
import logging
import importlib
from typing import Dict, Any, Optional, Type, List, Union, Tuple

from .abstract import AbstractMessenger

logger = logging.getLogger(__name__)


class MessagingService:
    """
    Unified messaging service that manages different messaging platform implementations.
    Provides a common interface to send messages across multiple platforms.
    """

    def __init__(self):
        self._messengers: Dict[str, AbstractMessenger] = {}
        
    def register_messenger(self, platform: str, messenger: AbstractMessenger) -> None:
        """
        Register a messenger implementation for a specific platform.

        Args:
            platform: Platform identifier (e.g., "telegram", "viber", "whatsapp")
            messenger: Instance of AbstractMessenger implementation for the platform
        """
        self._messengers[platform] = messenger
        logger.info(f"Registered messenger for platform: {platform}")

    def get_messenger(self, platform: str) -> Optional[AbstractMessenger]:
        """
        Get the messenger implementation for a specific platform.

        Args:
            platform: Platform identifier

        Returns:
            Messenger implementation or None if not registered
        """
        return self._messengers.get(platform)

    async def get_user_platform(self, user_id: int) -> Tuple[Optional[str], Optional[str]]:
        """
        Determine the platform and platform-specific ID for a user.

        Args:
            user_id: Database user ID

        Returns:
            Tuple of (platform, platform_specific_id) or (None, None) if not found
        """
        from common.db.database import execute_query
        
        sql = """
              SELECT telegram_id, viber_id, whatsapp_id
              FROM users
              WHERE id = %s
              """
        row = execute_query(sql, [user_id], fetchone=True)
        
        if not row:
            return None, None
            
        if row.get("telegram_id"):
            return "telegram", str(row["telegram_id"])
            
        if row.get("viber_id"):
            return "viber", row["viber_id"]
            
        if row.get("whatsapp_id"):
            return "whatsapp", row["whatsapp_id"]
            
        return None, None

    async def send_notification(
        self, 
        user_id: int, 
        text: str, 
        image_url: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Send a notification to a user using their preferred messenger.

        Args:
            user_id: Database user ID
            text: Message text
            image_url: Optional image URL
            **kwargs: Additional parameters for the messenger

        Returns:
            True if sent successfully, False otherwise
        """
        platform, platform_id = await self.get_user_platform(user_id)
        
        if not platform or not platform_id:
            logger.warning(f"No messaging platform found for user {user_id}")
            return False
            
        messenger = self.get_messenger(platform)
        if not messenger:
            logger.error(f"No messenger implementation for platform {platform}")
            return False
            
        try:
            formatted_id = await messenger.format_user_id(platform_id)
            
            if image_url:
                await messenger.send_image(formatted_id, image_url, caption=text, **kwargs)
            else:
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
            **kwargs: Additional parameters for the messenger

        Returns:
            True if sent successfully, False otherwise
        """
        platform, platform_id = await self.get_user_platform(user_id)
        
        if not platform or not platform_id:
            logger.warning(f"No messaging platform found for user {user_id}")
            return False
            
        messenger = self.get_messenger(platform)
        if not messenger:
            logger.error(f"No messenger implementation for platform {platform}")
            return False
            
        try:
            formatted_id = await messenger.format_user_id(platform_id)
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
        from .plugins.telegram import TelegramMessenger
        from .plugins.viber import ViberMessenger
        from .plugins.whatsapp import WhatsAppMessenger
        
        # Import bot instances from their respective services
        from services.telegram_service.app.bot import bot as telegram_bot
        from services.viber_service.app.bot import viber as viber_bot
        from services.whatsapp_service.app.bot import client as twilio_client
        
        service = cls()
        service.register_messenger("telegram", TelegramMessenger(telegram_bot))
        service.register_messenger("viber", ViberMessenger(viber_bot))
        service.register_messenger("whatsapp", WhatsAppMessenger(twilio_client))
        
        return service


# Create a singleton instance for global use
messaging_service = MessagingService.create_default()