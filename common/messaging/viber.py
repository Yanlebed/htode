# common/messaging/viber.py

from .abstract import AbstractMessenger
from typing import List, Dict, Any, Optional
from viberbot import Api
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage


class ViberMessenger(AbstractMessenger):
    """Viber implementation of the messenger abstraction"""

    def __init__(self, viber: Api):
        self.viber = viber

    def send_text(self, user_id: str, text: str, **kwargs) -> Any:
        """Send a text message via Viber"""
        return self.viber.send_messages(user_id, [
            TextMessage(text=text)
        ])

    def send_image(self, user_id: str, image_url: str, caption: Optional[str] = None, **kwargs) -> Any:
        """Send an image message via Viber"""
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

        return self.viber.send_messages(user_id, messages)

    def send_menu(self, user_id: str, text: str, options: List[Dict[str, str]], **kwargs) -> Any:
        """Send a menu with options via Viber"""
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

        return self.viber.send_messages(user_id, [
            TextMessage(text=text),
            KeyboardMessage(keyboard=keyboard)
        ])
