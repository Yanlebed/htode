# common/messaging/whatsapp_messaging.py

import logging
import asyncio
import os
from typing import Optional, List, Dict, Any, Union

from twilio.rest import Client

from .interface import MessagingInterface
from .utils import retry_with_exponential_backoff

logger = logging.getLogger(__name__)


class WhatsAppMessaging(MessagingInterface):
    """WhatsApp implementation of the messaging interface via Twilio."""

    def __init__(self, twilio_client: Client):
        """
        Initialize the WhatsApp messaging implementation.

        Args:
            twilio_client: Twilio Client instance
        """
        self.client = twilio_client
        # Get WhatsApp number from environment
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER")
        if not self.from_number:
            logger.warning("TWILIO_PHONE_NUMBER environment variable not set")
            self.from_number = ""

        # Ensure from_number has whatsapp: prefix
        if not self.from_number.startswith("whatsapp:"):
            self.from_number = f"whatsapp:{self.from_number}"

    def get_platform_name(self) -> str:
        """Get platform identifier."""
        return "whatsapp"

    async def format_user_id(self, user_id: str) -> str:
        """Format user ID for WhatsApp - add whatsapp: prefix if not present."""
        # Ensure proper WhatsApp formatting
        if not user_id.startswith("whatsapp:"):
            return f"whatsapp:{user_id}"
        return user_id

    @retry_with_exponential_backoff(max_retries=3, initial_delay=1)
    async def send_text(
            self,
            user_id: str,
            text: str,
            **kwargs
    ) -> Union[str, None]:
        """Send a text message via WhatsApp."""
        try:
            # Ensure user_id has whatsapp: prefix
            to_number = await self.format_user_id(user_id)

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
            raise  # Let the retry decorator handle this

    @retry_with_exponential_backoff(max_retries=3, initial_delay=1)
    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            **kwargs
    ) -> Union[str, None]:
        """Send a media message via WhatsApp."""
        try:
            # Ensure user_id has whatsapp: prefix
            to_number = await self.format_user_id(user_id)

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
            # Fall back to text if media fails but don't raise to retry
            if caption:
                try:
                    return await self.send_text(
                        user_id=user_id,
                        text=f"{caption}\n\n[Media URL: {media_url}]"
                    )
                except Exception:
                    pass
            raise  # Let the retry decorator handle the original error

    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Union[str, None]:
        """
        Send a menu with options via WhatsApp.

        Note: WhatsApp via Twilio doesn't support rich keyboards,
        so we format options as a text-based menu with instructions.
        """
        # Convert options to a text-based menu
        menu_text = self.create_keyboard(options, text_header=text)
        return await self.send_text(user_id, menu_text, **kwargs)

    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Union[str, None]:
        """Send a real estate ad via WhatsApp with appropriate formatting."""
        from common.config import build_ad_text

        # Build the ad text
        text = build_ad_text(ad_data)

        # Create instruction text for WhatsApp (no buttons support)
        ad_id = ad_data.get("id")

        text_with_instructions = (
            f"{text}\n\n"
            "Доступні дії:\n"
            f"- Відповідь 'фото {ad_id}' для більше фото\n"
            f"- Відповідь 'тел {ad_id}' для номерів телефону\n"
            f"- Відповідь 'обр {ad_id}' щоб додати в обрані\n"
            f"- Відповідь 'опис {ad_id}' для повного опису"
        )

        # Send the ad
        if image_url:
            return await self.send_media(
                user_id=user_id,
                media_url=image_url,
                caption=text_with_instructions,
                **kwargs
            )
        else:
            return await self.send_text(
                user_id=user_id,
                text=text_with_instructions,
                **kwargs
            )

    @classmethod
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            text_header: str = "",
            **kwargs
    ) -> str:
        """
        Create a text-based menu for WhatsApp since it doesn't support rich keyboards.

        Args:
            options: List of options with 'text' and 'value' keys
            text_header: Optional heading text for the menu
            **kwargs: Additional parameters (not used)

        Returns:
            Formatted text-based menu
        """
        # Format the options as a numbered list
        options_text = "\n".join([f"{i + 1}. {option['text']}" for i, option in enumerate(options)])

        # Combine title and options
        if text_header:
            return f"{text_header}\n\n{options_text}\n\nВведіть номер опції:"
        return f"{options_text}\n\nВведіть номер опції:"