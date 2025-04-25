"""
Telegram implementation of the messaging interface.
"""
import logging
from typing import Optional, List, Dict, Any, Union

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode

from .interface import MessagingInterface

logger = logging.getLogger(__name__)


class TelegramMessaging(MessagingInterface):
    """Telegram implementation of the messaging interface."""

    def __init__(self, bot: Bot):
        """
        Initialize the Telegram messaging implementation.

        Args:
            bot: Aiogram Bot instance
        """
        self.bot = bot

    async def send_text(
            self,
            user_id: str,
            text: str,
            parse_mode: Optional[str] = None,
            reply_markup: Optional[InlineKeyboardMarkup] = None,
            disable_web_page_preview: bool = False,
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """
        Send a text message via Telegram.

        Args:
            user_id: Telegram chat ID
            text: Message text
            parse_mode: Optional parse mode (Markdown or HTML)
            reply_markup: Optional inline keyboard
            disable_web_page_preview: Whether to disable web page previews
            **kwargs: Additional parameters to pass to Telegram API

        Returns:
            Message object or None if sending failed
        """
        try:
            message = await self.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
                **kwargs
            )
            return message
        except Exception as e:
            logger.error(f"Error sending Telegram message to {user_id}: {e}")
            return None

    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            parse_mode: Optional[str] = None,
            reply_markup: Optional[InlineKeyboardMarkup] = None,
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """
        Send an image via Telegram.

        Args:
            user_id: Telegram chat ID
            media_url: URL of the image
            caption: Optional image caption
            parse_mode: Optional parse mode for caption
            reply_markup: Optional inline keyboard
            **kwargs: Additional parameters to pass to Telegram API

        Returns:
            Message object or None if sending failed
        """
        try:
            message = await self.bot.send_photo(
                chat_id=user_id,
                photo=media_url,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                **kwargs
            )
            return message
        except Exception as e:
            logger.error(f"Error sending Telegram image to {user_id}: {e}")
            # Fall back to text if image fails
            if caption:
                return await self.send_text(
                    user_id=user_id,
                    text=f"{caption}\n\n[Image]({media_url})",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            return None

    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            parse_mode: Optional[str] = None,
            **kwargs
    ) -> Union[Dict[str, Any], None]:
        """
        Send a menu with options via Telegram.

        Args:
            user_id: Telegram chat ID
            text: Menu title or description
            options: List of options (dicts with 'text' and 'value' keys)
            parse_mode: Optional parse mode for text
            **kwargs: Additional parameters to pass to Telegram API

        Returns:
            Message object or None if sending failed
        """
        keyboard = self.create_keyboard(options)
        return await self.send_text(
            user_id=user_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=keyboard,
            **kwargs
        )

    def sanitize_user_id(self, user_id: str) -> str:
        """
        Ensure user ID is in the proper format for Telegram.

        Args:
            user_id: User identifier that may need formatting

        Returns:
            Properly formatted user ID
        """
        # Telegram IDs are numeric
        return str(user_id)

    @classmethod
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            row_width: int = 2,
            **kwargs
    ) -> InlineKeyboardMarkup:
        """
        Create a Telegram inline keyboard from options.

        Args:
            options: List of options (dicts with 'text' and 'value' keys)
            row_width: Number of buttons per row
            **kwargs: Additional parameters for keyboard creation

        Returns:
            Telegram InlineKeyboardMarkup
        """
        keyboard = InlineKeyboardMarkup(row_width=row_width)
        for option in options:
            button = InlineKeyboardButton(
                text=option['text'],
                callback_data=option.get('value'),
                url=option.get('url'),
                web_app=option.get('web_app')
            )
            keyboard.insert(button)
        return keyboard