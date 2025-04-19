# common/messaging/telegram.py

from .abstract import AbstractMessenger
from typing import List, Dict, Any, Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


class TelegramMessenger(AbstractMessenger):
    """Telegram implementation of the messenger abstraction"""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_text(self, user_id: str, text: str, **kwargs) -> Any:
        """Send a text message via Telegram"""
        return await self.bot.send_message(chat_id=user_id, text=text, **kwargs)

    async def send_image(self, user_id: str, image_url: str, caption: Optional[str] = None, **kwargs) -> Any:
        """Send an image message via Telegram"""
        return await self.bot.send_photo(chat_id=user_id, photo=image_url, caption=caption, **kwargs)

    async def send_menu(self, user_id: str, text: str, options: List[Dict[str, str]], **kwargs) -> Any:
        """Send a menu with options via Telegram"""
        markup = InlineKeyboardMarkup()
        for option in options:
            button = InlineKeyboardButton(text=option["text"], callback_data=option["value"])
            markup.add(button)

        return await self.bot.send_message(chat_id=user_id, text=text, reply_markup=markup, **kwargs)