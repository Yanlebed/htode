# common/messaging/telegram_messaging.py

import logging
from typing import Optional, List, Dict, Any, Union

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode, WebAppInfo
from aiogram.utils.exceptions import (
    MessageNotModified, BotBlocked, ChatNotFound,
    UserDeactivated, RetryAfter, TelegramAPIError
)

from .interface import MessagingInterface
from .utils import retry_with_exponential_backoff

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

    def get_platform_name(self) -> str:
        """Get platform identifier."""
        return "telegram"

    async def format_user_id(self, user_id: str) -> str:
        """Format user ID for Telegram - no special formatting needed."""
        return str(user_id)  # Ensure it's a string

    @retry_with_exponential_backoff(max_retries=3, initial_delay=1)
    async def send_text(
            self,
            user_id: str,
            text: str,
            keyboard: Optional[InlineKeyboardMarkup] = None,
            parse_mode: Optional[str] = None,
            disable_web_page_preview: bool = False,
            **kwargs
    ) -> Union[Any, None]:
        """Send a text message via Telegram."""
        try:
            return await self.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=parse_mode or ParseMode.MARKDOWN,
                disable_web_page_preview=disable_web_page_preview,
                **kwargs
            )
        except (BotBlocked, ChatNotFound, UserDeactivated) as e:
            # These are permanent errors, no need to retry
            logger.warning(f"Permanent error sending Telegram message to {user_id}: {e}")
            return None
        except TelegramAPIError as e:
            logger.error(f"Telegram API error sending message to {user_id}: {e}")
            raise  # Let the retry decorator handle this

    @retry_with_exponential_backoff(max_retries=3, initial_delay=1)
    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            keyboard: Optional[InlineKeyboardMarkup] = None,
            parse_mode: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """Send a media message via Telegram."""
        try:
            return await self.bot.send_photo(
                chat_id=user_id,
                photo=media_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode=parse_mode or ParseMode.MARKDOWN,
                **kwargs
            )
        except (BotBlocked, ChatNotFound, UserDeactivated) as e:
            # These are permanent errors, no need to retry
            logger.warning(f"Permanent error sending Telegram media to {user_id}: {e}")
            return None
        except TelegramAPIError as e:
            logger.error(f"Telegram API error sending media to {user_id}: {e}")
            raise  # Let the retry decorator handle this

    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            parse_mode: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """Send a menu with options via Telegram."""
        keyboard = self.create_keyboard(options, **kwargs)
        return await self.send_text(
            user_id=user_id,
            text=text,
            keyboard=keyboard,
            parse_mode=parse_mode,
            **kwargs
        )

    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """Send a real estate ad via Telegram with appropriate formatting."""
        from common.config import build_ad_text

        # Build the ad text
        text = build_ad_text(ad_data)

        # Create buttons for the ad
        resource_url = ad_data.get("resource_url")
        ad_id = ad_data.get("id")

        # Process images for gallery button
        gallery_url = None
        if "images" in ad_data and ad_data["images"]:
            images = ad_data["images"]
            if isinstance(images, list) and images:
                image_str = ",".join(images)
                gallery_url = f"https://f3cc-178-150-42-6.ngrok-free.app/gallery?images={image_str}"

        # Process phone numbers for call button
        phone_webapp_url = None
        if "phones" in ad_data and ad_data["phones"]:
            phones = ad_data["phones"]
            if isinstance(phones, list) and phones:
                phone_str = ",".join(phones)
                phone_webapp_url = f"https://f3cc-178-150-42-6.ngrok-free.app/phones?numbers={phone_str}"

        # Create buttons
        markup = InlineKeyboardMarkup(row_width=2)

        if gallery_url:
            markup.add(InlineKeyboardButton(
                text="🖼 Більше фото",
                web_app=WebAppInfo(url=gallery_url)
            ))

        if phone_webapp_url:
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
            return await self.send_media(
                user_id=user_id,
                media_url=image_url,
                caption=text,
                keyboard=markup,
                **kwargs
            )
        else:
            return await self.send_text(
                user_id=user_id,
                text=text,
                keyboard=markup,
                **kwargs
            )

    @classmethod
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            row_width: int = 2,
            **kwargs
    ) -> InlineKeyboardMarkup:
        """Create a Telegram inline keyboard from standardized options."""
        keyboard = InlineKeyboardMarkup(row_width=row_width)

        for option in options:
            button_params = {
                "text": option["text"],
                "callback_data": option.get("value", "")
            }

            # Handle different button types
            if "url" in option:
                button_params = {
                    "text": option["text"],
                    "url": option["url"]
                }
            elif "web_app" in option:
                button_params = {
                    "text": option["text"],
                    "web_app": WebAppInfo(url=option["web_app"])
                }

            button = InlineKeyboardButton(**button_params)
            keyboard.insert(button)

        return keyboard