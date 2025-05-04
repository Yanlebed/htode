# common/messaging/whatsapp_messaging.py

import asyncio
import os
from typing import Optional, List, Dict, Any, Union

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from .unified_interface import MessagingInterface
from common.utils.retry_utils import retry_with_exponential_backoff, NETWORK_EXCEPTIONS
from common.utils.logging_config import log_operation, log_context

# Import the messaging logger
from . import logger

TWILIO_EXCEPTIONS = [
    TwilioRestException,  # Base exception for Twilio API errors
]


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

    @property
    def platform_name(self) -> str:
        """Get platform identifier."""
        return "whatsapp"

    async def format_user_id(self, user_id: str) -> str:
        """Format user ID for WhatsApp - add whatsapp: prefix if not present."""
        # Ensure proper WhatsApp formatting
        if not user_id.startswith("whatsapp:"):
            return f"whatsapp:{user_id}"
        return user_id

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1,
        retryable_exceptions=TWILIO_EXCEPTIONS + NETWORK_EXCEPTIONS
    )
    @log_operation("send_text")
    async def send_text(
            self,
            user_id: str,
            text: str,
            **kwargs
    ) -> Union[str, None]:
        """Send a text message via WhatsApp."""
        with log_context(logger, user_id=user_id, platform="whatsapp", text_length=len(text)):
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

                logger.debug("Text message sent successfully", extra={
                    'user_id': user_id,
                    'message_sid': message.sid
                })
                return message.sid
            except Exception as e:
                logger.error(f"Error sending WhatsApp message", exc_info=True, extra={
                    'user_id': user_id,
                    'error_type': type(e).__name__
                })
                raise  # Let the retry decorator handle this

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1,
        retryable_exceptions=TWILIO_EXCEPTIONS + NETWORK_EXCEPTIONS
    )
    @log_operation("send_media")
    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            **kwargs
    ) -> Union[str, None]:
        """Send a media message via WhatsApp."""
        with log_context(logger, user_id=user_id, platform="whatsapp", media_url=media_url[:50]):
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

                logger.debug("Media message sent successfully", extra={
                    'user_id': user_id,
                    'message_sid': message.sid,
                    'has_caption': bool(caption)
                })
                return message.sid
            except Exception as e:
                logger.error(f"Error sending WhatsApp media", exc_info=True, extra={
                    'user_id': user_id,
                    'error_type': type(e).__name__
                })
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

    @log_operation("send_menu")
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
        with log_context(logger, user_id=user_id, platform="whatsapp", options_count=len(options)):
            # Convert options to a text-based menu
            menu_text = self.create_keyboard(options, text_header=text)
            return await self.send_text(user_id, menu_text, **kwargs)

    @log_operation("send_ad")
    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Union[str, None]:
        """Send a real estate ad via WhatsApp with appropriate formatting."""
        from common.config import build_ad_text

        with log_context(logger, user_id=user_id, platform="whatsapp", ad_id=ad_data.get("id")):
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