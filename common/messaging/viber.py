# common/messaging/viber.py

from .abstract import AbstractMessenger
from typing import List, Dict, Any, Optional
import asyncio
from viberbot import Api
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage


class ViberMessenger(AbstractMessenger):
    """Viber implementation of the messenger abstraction"""

    def __init__(self, viber: Api):
        self.viber = viber

    async def send_text(self, user_id: str, text: str, **kwargs) -> Any:
        """Send a text message via Viber asynchronously"""
        try:
            # Run the synchronous Viber API call in a thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self.viber.send_messages(user_id, [TextMessage(text=text)])
            )
        except Exception as e:
            print(f"Error sending Viber text message: {e}")
            return None

    async def send_image(self, user_id: str, image_url: str, caption: Optional[str] = None, **kwargs) -> Any:
        """Send an image message via Viber asynchronously"""
        messages = []

        # If we have a caption, send it as a separate message
        if caption:
            messages.append(TextMessage(text=caption))

        # Add the image
        messages.append(PictureMessage(
            media=image_url,
            text=caption or ""
        ))

        # Add keyboard if provided
        if "keyboard" in kwargs:
            messages.append(KeyboardMessage(keyboard=kwargs["keyboard"]))

        try:
            # Run the synchronous Viber API call in a thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self.viber.send_messages(user_id, messages)
            )
        except Exception as e:
            print(f"Error sending Viber image message: {e}")
            return None

    async def send_menu(self, user_id: str, text: str, options: List[Dict[str, str]], **kwargs) -> Any:
        """Send a menu with options via Viber asynchronously"""
        # Convert options to Viber keyboard format
        keyboard = {
            "Type": "keyboard",
            "Buttons": []
        }

        for option in options:
            button = {
                "Columns": 6,
                "Rows": 1,
                "Text": option["text"],
                "ActionType": "reply",
                "ActionBody": option["value"]
            }
            keyboard["Buttons"].append(button)

        try:
            # Run the synchronous Viber API call in a thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self.viber.send_messages(user_id, [
                    TextMessage(text=text),
                    KeyboardMessage(keyboard=keyboard)
                ])
            )
        except Exception as e:
            print(f"Error sending Viber menu message: {e}")
            return None