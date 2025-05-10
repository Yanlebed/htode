# common/messaging/telegram_messaging.py

from typing import Optional, List, Dict, Any, Union

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode, WebAppInfo
from aiogram.utils.exceptions import (
    MessageNotModified, BotBlocked, ChatNotFound,
    UserDeactivated, RetryAfter, TelegramAPIError
)

from .unified_interface import MessagingInterface
from common.utils.retry_utils import retry_with_exponential_backoff, NETWORK_EXCEPTIONS
from common.utils.logging_config import log_operation, log_context

# Import the logger from the parent module
from . import logger


class TelegramMessaging(MessagingInterface):
    """Telegram implementation of the messaging interface."""

    def __init__(self, bot: Bot):
        """
        Initialize the Telegram messaging implementation.

        Args:
            bot: Aiogram Bot instance
        """
        self.bot = bot

    @property
    def platform_name(self) -> str:
        """Get platform identifier."""
        return "telegram"

    @log_operation("format_user_id")
    async def format_user_id(self, user_id: str) -> str:
        """Format user ID for Telegram - no special formatting needed."""
        formatted_id = str(user_id)  # Ensure it's a string
        logger.debug("Formatted user ID", extra={
            'platform': 'telegram',
            'original_id': user_id[:10],
            'formatted_id': formatted_id[:10]
        })
        return formatted_id

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1,
        retryable_exceptions=[RetryAfter, TelegramAPIError] + NETWORK_EXCEPTIONS
    )
    @log_operation("send_text")
    async def send_text(
            self,
            user_id: str,
            text: str,
            reply_markup: Optional[InlineKeyboardMarkup] = None,
            parse_mode: Optional[str] = None,
            disable_web_page_preview: bool = False,
            **kwargs
    ) -> Union[Any, None]:
        """Send a text message via Telegram."""
        with log_context(logger, user_id=user_id[:10], text_length=len(text), has_keyboard=bool(reply_markup)):
            try:
                result = await self.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode or ParseMode.MARKDOWN,
                    disable_web_page_preview=disable_web_page_preview,
                    **kwargs
                )
                logger.info("Text message sent successfully", extra={
                    'user_id': user_id[:10],
                    'message_id': result.message_id if result else None
                })
                return result
            except (BotBlocked, ChatNotFound, UserDeactivated) as e:
                # These are permanent errors, no need to retry
                logger.warning(f"Permanent error sending Telegram message", extra={
                    'user_id': user_id[:10],
                    'error_type': type(e).__name__,
                    'error': str(e)
                })
                return None
            except TelegramAPIError as e:
                logger.error(f"Telegram API error sending message", exc_info=True, extra={
                    'user_id': user_id[:10],
                    'error_type': type(e).__name__
                })
                raise  # Let the retry decorator handle this

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1,
        retryable_exceptions=[RetryAfter, TelegramAPIError] + NETWORK_EXCEPTIONS
    )
    @log_operation("send_media")
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
        with log_context(logger, user_id=user_id[:10], media_url=media_url[:50], has_caption=bool(caption)):
            try:
                result = await self.bot.send_photo(
                    chat_id=user_id,
                    photo=media_url,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=parse_mode or ParseMode.MARKDOWN,
                    **kwargs
                )
                logger.info("Media message sent successfully", extra={
                    'user_id': user_id[:10],
                    'message_id': result.message_id if result else None
                })
                return result
            except (BotBlocked, ChatNotFound, UserDeactivated) as e:
                # These are permanent errors, no need to retry
                logger.warning(f"Permanent error sending Telegram media", extra={
                    'user_id': user_id[:10],
                    'error_type': type(e).__name__,
                    'error': str(e)
                })
                return None
            except TelegramAPIError as e:
                logger.error(f"Telegram API error sending media", exc_info=True, extra={
                    'user_id': user_id[:10],
                    'error_type': type(e).__name__
                })
                raise  # Let the retry decorator handle this

    @log_operation("send_menu")
    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            parse_mode: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """Send a menu with options via Telegram."""
        with log_context(logger, user_id=user_id[:10], options_count=len(options)):
            keyboard = self.create_keyboard(options, **kwargs)
            return await self.send_text(
                user_id=user_id,
                text=text,
                keyboard=keyboard,
                parse_mode=parse_mode,
                **kwargs
            )

    @log_operation("send_ad")
    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """Send a real estate ad via Telegram with appropriate formatting."""
        from common.config import build_ad_text

        with log_context(logger, user_id=user_id[:10], ad_id=ad_data.get('id')):
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
                result = await self.send_media(
                    user_id=user_id,
                    media_url=image_url,
                    caption=text,
                    keyboard=markup,
                    **kwargs
                )
            else:
                result = await self.send_text(
                    user_id=user_id,
                    text=text,
                    keyboard=markup,
                    **kwargs
                )

            logger.info("Ad sent successfully", extra={
                'user_id': user_id[:10],
                'ad_id': ad_id,
                'has_image': bool(image_url)
            })
            return result

    @classmethod
    @log_operation("create_keyboard")
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            row_width: int = 2,
            **kwargs
    ) -> InlineKeyboardMarkup:
        """Create a Telegram inline keyboard from standardized options."""
        with log_context(logger, options_count=len(options), row_width=row_width):
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

            logger.debug("Created Telegram keyboard", extra={
                'buttons_count': len(options),
                'row_width': row_width
            })
            return keyboard