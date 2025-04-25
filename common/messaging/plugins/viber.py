# common/messaging/plugins/viber.py

import logging
import asyncio
from typing import List, Dict, Any, Optional, Union

from viberbot import Api
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage

from ..abstract import AbstractMessenger
from ..utils import retry_with_exponential_backoff

logger = logging.getLogger(__name__)


class ViberMessenger(AbstractMessenger):
    """Viber implementation of the messenger abstraction"""

    def __init__(self, viber: Api):
        self.viber = viber

    @property
    def platform_name(self) -> str:
        return "viber"

    async def format_user_id(self, user_id: str) -> str:
        """
        Format user ID for Viber - no special formatting needed.

        Args:
            user_id: Viber user ID

        Returns:
            The same user ID (Viber doesn't need special formatting)
        """
        return user_id

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1
    )
    async def send_text(
            self,
            user_id: str,
            text: str,
            keyboard: Optional[Dict] = None,
            **kwargs
    ) -> Any:
        """
        Send a text message via Viber asynchronously.

        Args:
            user_id: Viber user ID
            text: Message text
            keyboard: Optional Viber keyboard dictionary
            **kwargs: Additional parameters

        Returns:
            API response dictionary
        """
        try:
            # Create message list
            messages = [TextMessage(text=text)]

            # Add keyboard if provided
            if keyboard:
                messages.append(KeyboardMessage(keyboard=keyboard))

            # Run the synchronous Viber API call in a thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.viber.send_messages(user_id, messages)
            )
            return response
        except Exception as e:
            logger.error(f"Error sending Viber text message: {e}")
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
            keyboard: Optional[Dict] = None,
            **kwargs
    ) -> Any:
        """
        Send an image message via Viber asynchronously.

        Args:
            user_id: Viber user ID
            image_url: URL of the image to send
            caption: Optional text caption
            keyboard: Optional Viber keyboard dictionary
            **kwargs: Additional parameters

        Returns:
            API response dictionary
        """
        messages = []

        # Add caption as separate text message if provided
        if caption:
            messages.append(TextMessage(text=caption))

        # Add the image
        messages.append(PictureMessage(
            media=image_url,
            text=caption or ""
        ))

        # Add keyboard if provided
        if keyboard:
            messages.append(KeyboardMessage(keyboard=keyboard))

        try:
            # Run the synchronous Viber API call in a thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.viber.send_messages(user_id, messages)
            )
            return response
        except Exception as e:
            logger.error(f"Error sending Viber image message: {e}")
            raise

    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Any:
        """
        Send a menu with options via Viber asynchronously.

        Args:
            user_id: Viber user ID
            text: Message text
            options: List of option dictionaries with 'text' and 'value' keys
            **kwargs: Additional parameters

        Returns:
            API response dictionary
        """
        # Convert options to Viber keyboard format
        keyboard = {
            "Type": "keyboard",
            "Buttons": []
        }

        # Set default button size if not specified
        button_columns = kwargs.get("button_columns", 6)
        button_rows = kwargs.get("button_rows", 1)

        for option in options:
            button = {
                "Columns": button_columns,
                "Rows": button_rows,
                "Text": option["text"],
                "ActionType": "reply",
                "ActionBody": option["value"]
            }

            # Add optional properties if available
            if "color" in option:
                button["BgColor"] = option["color"]

            if "image" in option:
                button["Image"] = option["image"]

            keyboard["Buttons"].append(button)

        try:
            # Send text with keyboard
            return await self.send_text(
                user_id=user_id,
                text=text,
                keyboard=keyboard
            )
        except Exception as e:
            logger.error(f"Error sending Viber menu: {e}")
            raise

    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Any:
        """
        Send a real estate ad with Viber-specific formatting.

        Args:
            user_id: Viber user ID
            ad_data: Dictionary with ad information
            image_url: Optional primary image URL
            **kwargs: Additional parameters

        Returns:
            API response dictionary
        """
        from common.config import build_ad_text

        # Build the ad text
        text = build_ad_text(ad_data)

        # Create buttons for the ad
        ad_id = ad_data.get("id")
        resource_url = ad_data.get("resource_url")

        # Create the Viber keyboard
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
            return await self.send_image(
                user_id=user_id,
                image_url=image_url,
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

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a Viber user.
        Note: Viber API has limited capabilities for fetching user details.

        Args:
            user_id: Viber user ID

        Returns:
            Dictionary with user information or None if unavailable
        """
        try:
            # Viber doesn't provide a direct way to get user info by ID
            # You would typically get this info when the user interacts with the bot
            # This implementation relies on info stored in your database

            # Query your database for user info using user_id
            from common.db.database import execute_query

            sql = """
                  SELECT name, avatar, country, language, api_version
                  FROM viber_user_details
                  WHERE user_id = %s
                  """

            user_info = execute_query(sql, [user_id], fetchone=True)

            if user_info:
                return {
                    "id": user_id,
                    "name": user_info.get("name"),
                    "avatar": user_info.get("avatar"),
                    "country": user_info.get("country"),
                    "language": user_info.get("language")
                }
            return None

        except Exception as e:
            logger.error(f"Error getting Viber user info for {user_id}: {e}")
            return None