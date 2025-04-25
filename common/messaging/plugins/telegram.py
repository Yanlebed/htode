# common/messaging/plugins/telegram_messaging.py

import logging
import asyncio
from typing import List, Dict, Any, Optional, Union

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from aiogram.utils.exceptions import (
    MessageNotModified, BotBlocked, ChatNotFound,
    UserDeactivated, RetryAfter, TelegramAPIError
)

from ..abstract import AbstractMessenger
from ..utils import retry_with_exponential_backoff

logger = logging.getLogger(__name__)


class TelegramMessenger(AbstractMessenger):
    """Telegram implementation of the messenger abstraction"""

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def platform_name(self) -> str:
        return "telegram"

    async def format_user_id(self, user_id: str) -> str:
        """
        Format user ID for Telegram - no special formatting needed.

        Args:
            user_id: Telegram user ID

        Returns:
            The same user ID (Telegram doesn't need special formatting)
        """
        return user_id

    @retry_with_exponential_backoff(
        retryable_exceptions=[NetworkError, RetryAfter, ConnectionError],
        max_retries=3,
        initial_delay=1
    )
    async def send_text(
            self,
            user_id: str,
            text: str,
            reply_markup: Optional[InlineKeyboardMarkup] = None,
            parse_mode: Optional[str] = None,
            disable_web_page_preview: bool = False,
            **kwargs
    ) -> Any:
        """
        Send a text message via Telegram with retry logic.

        Args:
            user_id: Telegram chat ID
            text: Message text
            reply_markup: Optional inline keyboard
            parse_mode: Optional parse mode (Markdown, HTML)
            disable_web_page_preview: Whether to disable link previews
            **kwargs: Additional parameters

        Returns:
            Sent message object

        Raises:
            BotBlocked: User blocked the bot
            ChatNotFound: Chat not found
            UserDeactivated: User account deactivated
            TelegramAPIError: Other Telegram API errors
        """
        try:
            return await self.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                **kwargs
            )
        except (BotBlocked, ChatNotFound, UserDeactivated) as e:
            # These are permanent errors, don't retry
            logger.warning(f"Permanent error sending message to {user_id}: {e}")
            raise
        except TelegramAPIError as e:
            logger.error(f"Telegram API error sending message to {user_id}: {e}")
            raise

    @retry_with_exponential_backoff(
        retryable_exceptions=[NetworkError, RetryAfter, ConnectionError],
        max_retries=3,
        initial_delay=1
    )
    async def send_image(
            self,
            user_id: str,
            image_url: str,
            caption: Optional[str] = None,
            reply_markup: Optional[InlineKeyboardMarkup] = None,
            parse_mode: Optional[str] = None,
            **kwargs
    ) -> Any:
        """
        Send an image message via Telegram with retry logic.

        Args:
            user_id: Telegram chat ID
            image_url: URL of the image to send
            caption: Optional text caption
            reply_markup: Optional inline keyboard
            parse_mode: Optional parse mode for caption
            **kwargs: Additional parameters

        Returns:
            Sent message object

        Raises:
            BotBlocked: User blocked the bot
            ChatNotFound: Chat not found
            UserDeactivated: User account deactivated
            TelegramAPIError: Other Telegram API errors
        """
        try:
            return await self.bot.send_photo(
                chat_id=user_id,
                photo=image_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs
            )
        except (BotBlocked, ChatNotFound, UserDeactivated) as e:
            # These are permanent errors, don't retry
            logger.warning(f"Permanent error sending image to {user_id}: {e}")
            raise
        except TelegramAPIError as e:
            logger.error(f"Telegram API error sending image to {user_id}: {e}")
            raise

    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Any:
        """
        Send a menu with options via Telegram.

        Args:
            user_id: Telegram chat ID
            text: Message text
            options: List of option dictionaries with 'text' and 'value' keys
            **kwargs: Additional parameters

        Returns:
            Sent message object
        """
        # Create an inline keyboard from the options
        markup = InlineKeyboardMarkup(row_width=1)
        for option in options:
            button = InlineKeyboardButton(
                text=option["text"],
                callback_data=option["value"]
            )
            # Handle special button types
            if "url" in option:
                button = InlineKeyboardButton(
                    text=option["text"],
                    url=option["url"]
                )
            elif "web_app" in option:
                from aiogram.types import WebAppInfo
                button = InlineKeyboardButton(
                    text=option["text"],
                    web_app=WebAppInfo(url=option["web_app"])
                )

            markup.add(button)

        # Send the message with the inline keyboard
        return await self.send_text(
            user_id=user_id,
            text=text,
            reply_markup=markup,
            **kwargs
        )

    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Any:
        """
        Send a real estate ad with Telegram-specific formatting.

        Args:
            user_id: Telegram chat ID
            ad_data: Dictionary with ad information
            image_url: Optional primary image URL
            **kwargs: Additional parameters

        Returns:
            Sent message object
        """
        from common.config import build_ad_text

        # Build the ad text
        text = build_ad_text(ad_data)

        # Create buttons for the ad
        resource_url = ad_data.get("resource_url")
        ad_id = ad_data.get("id")

        # Prepare image gallery URL if there are images
        gallery_url = None
        if "images" in ad_data and ad_data["images"]:
            image_str = ",".join(ad_data["images"])
            gallery_url = f"https://example.com/gallery?images={image_str}"

        # Prepare phone numbers URL if available
        phone_webapp_url = None
        if "phones" in ad_data and ad_data["phones"]:
            phone_str = ",".join(ad_data["phones"])
            phone_webapp_url = f"https://example.com/phones?numbers={phone_str}"

        # Create the inline keyboard
        markup = InlineKeyboardMarkup(row_width=2)

        if gallery_url:
            from aiogram.types import WebAppInfo
            markup.add(InlineKeyboardButton(
                text="🖼 Більше фото",
                web_app=WebAppInfo(url=gallery_url)
            ))

        if phone_webapp_url:
            from aiogram.types import WebAppInfo
            markup.add(InlineKeyboardButton(
                text="📲 Подзвонити",
                web_app=WebAppInfo(url=phone_webapp_url)
            ))

        markup.add(
            InlineKeyboardButton("❤️ Додати в обрані", callback_data=f"add_fav:{ad_id}"),
            InlineKeyboardButton("ℹ️ Повний опис", callback_data=f"show_more:{resource_url}")
        )

        # Send the ad
        if image_url:
            return await self.send_image(
                user_id=user_id,
                image_url=image_url,
                caption=text,
                reply_markup=markup,
                parse_mode='Markdown',
                **kwargs
            )
        else:
            return await self.send_text(
                user_id=user_id,
                text=text,
                reply_markup=markup,
                parse_mode='Markdown',
                **kwargs
            )

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a Telegram user.

        Args:
            user_id: Telegram user ID

        Returns:
            Dictionary with user information or None if unavailable
        """
        try:
            chat = await self.bot.get_chat(chat_id=user_id)
            return {
                "id": chat.id,
                "username": chat.username,
                "first_name": chat.first_name,
                "last_name": chat.last_name,
                "type": chat.type
            }
        except Exception as e:
            logger.error(f"Error getting user info for {user_id}: {e}")
            return None