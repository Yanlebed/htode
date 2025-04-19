# common/messaging/service.py
import logging

from typing import Optional, Tuple, Dict, Any
from common.db.database import execute_query
from .telegram import TelegramMessenger
from .viber import ViberMessenger
from .whatsapp import WhatsAppMessenger

logger = logging.getLogger(__name__)


class MessagingService:
    """Service to determine and use the appropriate messenger for a user"""

    def __init__(self, telegram_messenger: TelegramMessenger, viber_messenger: ViberMessenger,
                 whatsapp_messenger: WhatsAppMessenger):
        self.telegram_messenger = telegram_messenger
        self.viber_messenger = viber_messenger
        self.whatsapp_messenger = whatsapp_messenger

    def get_user_messenger(self, user_id: int) -> Tuple[Optional[str], Optional[str]]:
        """
        Get the messenger type and ID for a user

        Returns:
            Tuple of (messenger_type, messenger_id) or (None, None) if not found
        """
        sql = """
              SELECT telegram_id, viber_id, whatsapp_id
              FROM users
              WHERE id = %s \
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

    async def send_notification(self, user_id: int, text: str, **kwargs) -> bool:
        """
        Send a notification to a user using their preferred messenger

        Args:
            user_id: Database user ID
            text: Message text
            **kwargs: Additional parameters for the messenger

        Returns:
            True if sent successfully, False otherwise
        """
        messenger_type, messenger_id = self.get_user_messenger(user_id)

        if not messenger_type or not messenger_id:
            return False

        try:
            if messenger_type == "telegram":
                await self.telegram_messenger.send_text(messenger_id, text, **kwargs)
            elif messenger_type == "viber":
                await self.viber_messenger.send_text(messenger_id, text, **kwargs)  # Now using await
            elif messenger_type == "whatsapp":
                await self.whatsapp_messenger.send_text(messenger_id, text, **kwargs)  # Now using await
            return True
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")
            return False