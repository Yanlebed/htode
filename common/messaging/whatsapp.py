"""
WhatsApp implementation of the messaging interface using Twilio.
"""
import logging
import asyncio
from typing import Optional, List, Dict, Any, Union

from twilio.rest import Client

from .interface import MessagingInterface

logger = logging.getLogger(__name__)


class WhatsAppMessaging(MessagingInterface):
    """WhatsApp implementation of the messaging interface via Twilio."""

    def __init__(self, twilio_client: Client, from_number: str):
        """
        Initialize the WhatsApp messaging implementation.

        Args:
            twilio_client: Twilio Client instance
            from_number: WhatsApp number to send from (with whatsapp: prefix)
        """
        self.client = twilio_client
        self.from_number = from_number

        # Ensure from_number has whatsapp: prefix
        if not self.from_number.startswith("whatsapp:"):
            self.from_number = f"whatsapp:{self.from_number}"

    async def send_text(
            self,
            user_id: str,
            text: str,
            **kwargs
    ) -> Union[str, None]:
        """
        Send a text message via WhatsApp.

        Args:
            user_id: WhatsApp number (with or without whatsapp: prefix)
            text: Message text
            **kwargs: Additional parameters to pass to Twilio API

        Returns:
            Message SID or None if sending failed
        """
        try:
            # Ensure user_id has whatsapp: prefix
            to_number = self.sanitize_user_id(user_id)

            # Execute in thread pool since Twilio API is synchronous
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    from_=self.from_number,
                    body=text,
                    to=to_number,
                    **kwargs
                )
            )
            return message.sid
        except Exception as e:
            logger.error(f"Error sending WhatsApp message to {user_id}: {e}")
            return None

    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            **kwargs
    ) -> Union[str, None]:
        """
        Send a media message via WhatsApp.

        Args:
            user_id: WhatsApp number (with or without whatsapp: prefix)
            media_url: URL of the media to send
            caption: Optional text caption
            **kwargs: Additional parameters to pass to Twilio API

        Returns:
            Message SID or None if sending failed
        """
        try:
            # Ensure user_id has whatsapp: prefix
            to_number = self.sanitize_user_id(user_id)

            # Execute in thread pool since Twilio API is synchronous
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    from_=self.from_number,
                    body=caption or "",
                    media_url=[media_url],
                    to=to_number,
                    **kwargs
                )
            )
            return message.sid
        except Exception as e:
            logger.error(f"Error sending WhatsApp media to {user_id}: {e}")
            # Fall back to text if media fails
            if caption:
                return await self.send_text(user_id, f"{caption}\n\n[Media URL: {media_url}]")
            return None

    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Union[str, None]:
        """
        Send a menu with options via WhatsApp.

        Args:
            user_id: WhatsApp number (with or without whatsapp: prefix)
            text: Menu title or description
            options: List of options (dicts with 'text' and 'value' keys)
            **kwargs: Additional parameters to pass to Twilio API

        Returns:
            Message SID or None if sending failed
        """
        # WhatsApp via Twilio doesn't support rich keyboards,
        # so we'll create a text-based menu
        menu_text = self.create_keyboard(options, menu_title=text)
        return await self.send_text(user_id, menu_text, **kwargs)

    def sanitize_user_id(self, user_id: str) -> str:
        """
        Ensure user ID is in the proper format for WhatsApp.

        Args:
            user_id: WhatsApp number (with or without whatsapp: prefix)

        Returns:
            Properly formatted WhatsApp number with whatsapp: prefix
        """
        # Ensure user_id has whatsapp: prefix
        if not user_id.startswith("whatsapp:"):
            return f"whatsapp:{user_id}"
        return user_id

    @classmethod
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            menu_title: str = "",
            **kwargs
    ) -> str:
        """
        Create a text-based menu for WhatsApp.

        Args:
            options: List of options (dicts with 'text' and 'value' keys)
            menu_title: Optional title for the menu
            **kwargs: Additional parameters (not used)

        Returns:
            Formatted text-based menu
        """
        # Format the options as a numbered list
        options_text = "\n".join([f"{i + 1}. {option['text']}" for i, option in enumerate(options)])

        # Combine title and options
        if menu_title:
            return f"{menu_title}\n\n{options_text}\n\nВведіть номер опції:"
        return f"{options_text}\n\nВведіть номер опції:"