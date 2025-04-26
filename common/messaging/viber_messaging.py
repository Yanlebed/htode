# common/messaging/viber_messaging.py

import logging
import asyncio
from typing import Optional, List, Dict, Any, Union

from viberbot import Api
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage

from .unified_interface import MessagingInterface
from common.utils.retry_utils import retry_with_exponential_backoff, NETWORK_EXCEPTIONS

logger = logging.getLogger(__name__)


class ViberMessaging(MessagingInterface):
    """Viber implementation of the messaging interface."""

    def __init__(self, viber_api: Api):
        """
        Initialize the Viber messaging implementation.

        Args:
            viber_api: Viber API client instance
        """
        self.viber = viber_api

    def get_platform_name(self) -> str:
        """Get platform identifier."""
        return "viber"

    async def format_user_id(self, user_id: str) -> str:
        """Format user ID for Viber - no special formatting needed."""
        return user_id

    @retry_with_exponential_backoff(max_retries=3, initial_delay=1, retryable_exceptions=NETWORK_EXCEPTIONS)
    async def send_text(
            self,
            user_id: str,
            text: str,
            keyboard: Optional[Dict[str, Any]] = None,
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """Send a text message via Viber."""
        try:
            messages = [TextMessage(text=text)]

            if keyboard:
                messages.append(KeyboardMessage(keyboard=keyboard))

            # Execute in thread pool since Viber API is synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.viber.send_messages(user_id, messages)
            )
            return response
        except Exception as e:
            logger.error(f"Error sending Viber message to {user_id}: {e}")
            raise  # Let the retry decorator handle this

    @retry_with_exponential_backoff(max_retries=3, initial_delay=1, retryable_exceptions=NETWORK_EXCEPTIONS)
    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            keyboard: Optional[Dict[str, Any]] = None,
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """Send a media message via Viber."""
        try:
            messages = []

            # Add caption as a separate message if provided
            if caption:
                messages.append(TextMessage(text=caption))

            # Add the image
            messages.append(PictureMessage(
                media=media_url,
                text=caption or ""
            ))

            # Add keyboard if provided
            if keyboard:
                messages.append(KeyboardMessage(keyboard=keyboard))

            # Execute in thread pool since Viber API is synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.viber.send_messages(user_id, messages)
            )
            return response
        except Exception as e:
            logger.error(f"Error sending Viber media to {user_id}: {e}")
            # Fallback to text if media fails but don't raise to retry
            if caption:
                try:
                    return await self.send_text(
                        user_id=user_id,
                        text=f"{caption}\n\n[Image URL: {media_url}]",
                        keyboard=keyboard
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
    ) -> Union[Dict[str, Any], None]:
        """Send a menu with options via Viber."""
        keyboard = self.create_keyboard(options, **kwargs)
        return await self.send_text(
            user_id=user_id,
            text=text,
            keyboard=keyboard,
            **kwargs
        )

    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """Send a real estate ad via Viber with appropriate formatting."""
        from common.config import build_ad_text

        # Build the ad text
        text = build_ad_text(ad_data)

        # Create buttons for the ad
        ad_id = ad_data.get("id")
        resource_url = ad_data.get("resource_url")

        # Create Viber keyboard
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

        # Send the ad
        if image_url:
            return await self.send_media(
                user_id=user_id,
                media_url=image_url,
                caption=text,
                keyboard=keyboard,
                **kwargs
            )
        else:
            return await self.send_text(
                user_id=user_id,
                text=text,
                keyboard=keyboard,
                **kwargs
            )

    @classmethod
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            columns: int = 6,
            rows: int = 1,
            buttons_group_columns: int = 6,
            buttons_group_rows: int = 5,
            **kwargs
    ) -> Dict[str, Any]:
        """Create a Viber keyboard from standardized options."""
        buttons = []

        for option in options:
            button = {
                "Columns": option.get("columns", columns),
                "Rows": option.get("rows", rows),
                "Text": option["text"],
                "ActionType": "reply",
                "ActionBody": option.get("value", option["text"])
            }

            # Add URL if present
            if "url" in option:
                button["ActionType"] = "open-url"
                button["ActionBody"] = option["url"]

            # Add color if present
            if "color" in option:
                button["BgColor"] = option["color"]

            # Add image if present
            if "image" in option:
                button["Image"] = option["image"]

            buttons.append(button)

        return {
            "Type": "keyboard",
            "ButtonsGroupColumns": kwargs.get("ButtonsGroupColumns", buttons_group_columns),
            "ButtonsGroupRows": kwargs.get("ButtonsGroupRows", buttons_group_rows),
            "Buttons": buttons
        }