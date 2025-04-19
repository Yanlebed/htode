# common/messaging/whatsapp.py

from .abstract import AbstractMessenger
from typing import List, Dict, Any, Optional
import os


class WhatsAppMessenger(AbstractMessenger):
    """WhatsApp implementation of the messenger abstraction using Twilio"""

    def __init__(self, twilio_client):
        self.twilio_client = twilio_client
        self.whatsapp_number = os.getenv("TWILIO_PHONE_NUMBER")
        if not self.whatsapp_number:
            raise ValueError("TWILIO_PHONE_NUMBER environment variable not set")

    def send_text(self, user_id: str, text: str, **kwargs) -> Any:
        """Send a text message via WhatsApp"""
        # Ensure proper WhatsApp formatting
        if not user_id.startswith("whatsapp:"):
            user_id = f"whatsapp:{user_id}"

        try:
            message = self.twilio_client.messages.create(
                from_=self.whatsapp_number,
                body=text,
                to=user_id
            )
            return message.sid
        except Exception as e:
            print(f"Error sending WhatsApp message: {e}")
            return None

    def send_image(self, user_id: str, image_url: str, caption: Optional[str] = None, **kwargs) -> Any:
        """Send an image message via WhatsApp"""
        # Ensure proper WhatsApp formatting
        if not user_id.startswith("whatsapp:"):
            user_id = f"whatsapp:{user_id}"

        try:
            message = self.twilio_client.messages.create(
                from_=self.whatsapp_number,
                body=caption or "",
                media_url=[image_url],
                to=user_id
            )
            return message.sid
        except Exception as e:
            print(f"Error sending WhatsApp image: {e}")
            return None

    def send_menu(self, user_id: str, text: str, options: List[Dict[str, str]], **kwargs) -> Any:
        """
        Send a menu with options via WhatsApp

        Since WhatsApp doesn't support rich keyboards, this creates a text-based menu
        """
        # Format the options as a numbered list
        options_text = "\n".join([f"{i + 1}. {option['text']}" for i, option in enumerate(options)])
        full_text = f"{text}\n\n{options_text}"

        return self.send_text(user_id, full_text, **kwargs)