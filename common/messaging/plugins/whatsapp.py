# common/messaging/plugins/whatsapp_messaging.py

import logging
import asyncio
from typing import List, Dict, Any, Optional, Union

from twilio.rest import Client

from ..abstract import AbstractMessenger
from ..utils import retry_with_exponential_backoff

logger = logging.getLogger(__name__)


class WhatsAppMessenger(AbstractMessenger):
    """WhatsApp implementation of the messenger abstraction using Twilio"""

    def __init__(self, twilio_client: Client):
        self.twilio_client = twilio_client
        # Get WhatsApp number from environment
        import os
        self.whatsapp_number = os.getenv("TWILIO_PHONE_NUMBER")
        if not self.whatsapp_number:
            raise ValueError("TWILIO_PHONE_NUMBER environment variable not set")

    @property
    def platform_name(self) -> str:
        return "whatsapp"

    async def format_user_id(self, user_id: str) -> str:
        """
        Format user ID for WhatsApp - add 'whatsapp:' prefix if not present.

        Args:
            user_id: WhatsApp number

        Returns:
            Formatted WhatsApp number with 'whatsapp:' prefix
        """
        # Ensure proper WhatsApp formatting
        if not user_id.startswith("whatsapp:"):
            return f"whatsapp:{user_id}"
        return user_id

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1
    )
    async def send_text(
            self,
            user_id: str,
            text: str,
            **kwargs
    ) -> Any:
        """
        Send a text message via WhatsApp asynchronously.

        Args:
            user_id: WhatsApp number (with or without 'whatsapp:' prefix)
            text: Message text
            **kwargs: Additional parameters

        Returns:
            Twilio message SID
        """
        # Ensure proper WhatsApp formatting
        formatted_user_id = await self.format_user_id(user_id)

        try:
            # Run the synchronous Twilio API call in a thread pool
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.twilio_client.messages.create(
                    from_=self.whatsapp_number,
                    body=text,
                    to=formatted_user_id
                )
            )
            return message.sid
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            raise

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1
    )
    async def send_image(
            self,
            user_id: str,
            image_url: str,
            caption: Optional[str] = None,
            **kwargs
    ) -> Any:
        """
        Send an image message via WhatsApp asynchronously.

        Args:
            user_id: WhatsApp number
            image_url: URL of the image to send
            caption: Optional text caption
            **kwargs: Additional parameters

        Returns:
            Twilio message SID
        """
        # Ensure proper WhatsApp formatting
        formatted_user_id = await self.format_user_id(user_id)

        try:
            # Run the synchronous Twilio API call in a thread pool
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.twilio_client.messages.create(
                    from_=self.whatsapp_number,
                    body=caption or "",
                    media_url=[image_url],
                    to=formatted_user_id
                )
            )
            return message.sid
        except Exception as e:
            logger.error(f"Error sending WhatsApp image: {e}")
            raise

    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Any:
        """
        Send a menu with options via WhatsApp asynchronously.

        Note: WhatsApp doesn't support rich keyboards like Telegram or Viber,
        so this creates a text-based menu with numbered options.

        Args:
            user_id: WhatsApp number
            text: Message text
            options: List of option dictionaries with 'text' and 'value' keys
            **kwargs: Additional parameters

        Returns:
            Twilio message SID
        """
        # Format the options as a numbered list
        options_text = "\n".join([f"{i + 1}. {option['text']}" for i, option in enumerate(options)])
        full_text = f"{text}\n\n{options_text}\n\nВведіть номер опції для вибору."

        return await self.send_text(user_id, full_text, **kwargs)

    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Any:
        """
        Send a real estate ad with WhatsApp-specific formatting.

        Args:
            user_id: WhatsApp number
            ad_data: Dictionary with ad information
            image_url: Optional primary image URL
            **kwargs: Additional parameters

        Returns:
            Twilio message SID
        """
        from common.config import build_ad_text

        # Build the ad text
        text = build_ad_text(ad_data)

        # Add action instructions since WhatsApp doesn't support buttons
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
            return await self.send_image(
                user_id=user_id,
                image_url=image_url,
                caption=text_with_instructions,
                **kwargs
            )
        else:
            return await self.send_text(
                user_id=user_id,
                text=text_with_instructions,
                **kwargs
            )

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a WhatsApp user.
        Note: WhatsApp/Twilio API has limited capabilities for fetching user details.

        Args:
            user_id: WhatsApp number

        Returns:
            Dictionary with user information or None if unavailable
        """
        try:
            # WhatsApp via Twilio doesn't provide a direct way to get user info
            # This implementation returns basic info from the user_id itself

            # Strip the "whatsapp:" prefix if present
            phone_number = user_id
            if phone_number.startswith("whatsapp:"):
                phone_number = phone_number[9:]

            # Return basic info
            return {
                "id": user_id,
                "phone_number": phone_number,
                "platform": "whatsapp"
            }
        except Exception as e:
            logger.error(f"Error getting WhatsApp user info for {user_id}: {e}")
            return None