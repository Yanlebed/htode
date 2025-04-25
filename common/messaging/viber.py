"""
Viber implementation of the messaging interface.
"""
import logging
import asyncio
from typing import Optional, List, Dict, Any, Union

from viberbot import Api
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage

from .interface import MessagingInterface

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

    async def send_text(
            self,
            user_id: str,
            text: str,
            keyboard: Optional[Dict[str, Any]] = None,
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """
        Send a text message via Viber.

        Args:
            user_id: Viber user ID
            text: Message text
            keyboard: Optional Viber keyboard
            **kwargs: Additional parameters

        Returns:
            Response dict or None if sending failed
        """
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
            return None

    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            keyboard: Optional[Dict[str, Any]] = None,
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """
        Send an image via Viber.

        Args:
            user_id: Viber user ID
            media_url: URL of the image
            caption: Optional image caption
            keyboard: Optional Viber keyboard
            **kwargs: Additional parameters

        Returns:
            Response dict or None if sending failed
        """
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
            logger.error(f"Error sending Viber image to {user_id}: {e}")
            # Fall back to text if image fails
            if caption:
                return await self.send_text(user_id, f"{caption}\n\n[Image URL: {media_url}]", keyboard)
            return None

    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """
        Send a menu with options via Viber.

        Args:
            user_id: Viber user ID
            text: Menu title or description
            options: List of options (dicts with 'text' and 'value' keys)
            **kwargs: Additional parameters

        Returns:
            Response dict or None if sending failed
        """
        keyboard = self.create_keyboard(options, **kwargs)
        return await self.send_text(user_id, text, keyboard)

    def sanitize_user_id(self, user_id: str) -> str:
        """
        Ensure user ID is in the proper format for Viber.

        Args:
            user_id: User identifier that may need formatting

        Returns:
            Properly formatted user ID
        """
        # Viber doesn't need special formatting
        return user_id

    @classmethod
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            columns: int = 6,
            rows: int = 1,
            **kwargs
    ) -> Dict[str, Any]:
        """
        Create a Viber keyboard from options.

        Args:
            options: List of options (dicts with 'text' and 'value' keys)
            columns: Number of columns for button (default 6)
            rows: Number of rows for each button (default 1)
            **kwargs: Additional keyboard parameters

        Returns:
            Viber keyboard dict
        """
        buttons = []
        for option in options:
            button = {
                "Columns": option.get("columns", columns),
                "Rows": option.get("rows", rows),
                "Text": option["text"],
                "ActionType": "reply",
                "ActionBody": option["value"]
            }

            # Add URL if present
            if "url" in option:
                button["ActionType"] = "open-url"
                button["ActionBody"] = option["url"]

            buttons.append(button)

        return {
            "Type": "keyboard",
            "ButtonsGroupColumns": kwargs.get("ButtonsGroupColumns", 6),
            "ButtonsGroupRows": kwargs.get("ButtonsGroupRows", 5),
            "Buttons": buttons
        }