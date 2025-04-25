# services/telegram_service/app/tasks.py
import asyncio
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MediaGroup, CallbackQuery, WebAppInfo
from common.celery_app import celery_app
from .bot import bot, dp
from common.db.models import get_full_ad_description
from .utils.message_utils import (
    safe_answer_callback_query,
    delete_message_safe
)
from common.messaging.tasks import (
    send_ad_with_extra_buttons as unified_send_ad,
    send_subscription_notification as unified_send_notification,
    check_expiring_subscriptions as unified_check_subscriptions,
    process_show_more_description as unified_process_show_more
)

logger = logging.getLogger(__name__)


# Redirect to unified implementation
@celery_app.task(name='telegram_service.app.tasks.send_subscription_reminders')
def send_subscription_reminders():
    """
    Redirects to the unified check_expiring_subscriptions task.
    Kept for backward compatibility.
    """
    return unified_check_subscriptions.delay()


# Redirect to unified implementation
@celery_app.task(name='telegram_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id):
    """
    Redirects to the unified send_ad_with_extra_buttons task.
    Specifies 'telegram' as the platform for proper handling.
    Kept for backward compatibility.
    """
    return unified_send_ad.delay(
        user_id=user_id,
        text=text,
        s3_image_url=s3_image_url,
        resource_url=resource_url,
        ad_id=ad_id,
        ad_external_id=ad_external_id,
        platform="telegram"
    )


@dp.callback_query_handler(lambda c: c.data.startswith("show_more:"))
async def handle_show_more(callback_query: CallbackQuery):
    """
    Handle the show_more callback query and delegate to the unified task.
    This remains in the Telegram service as it's tied to the callback query handler.
    """
    # Extract the resource_url from the callback data
    try:
        _, resource_url = callback_query.data.split("show_more:")
    except Exception:
        await safe_answer_callback_query(
            callback_query_id=callback_query.id,
            text="Невірні дані.",
            show_alert=True
        )
        return

    # Acknowledge the callback query immediately
    await safe_answer_callback_query(
        callback_query_id=callback_query.id,
        text="Отримання повного опису..."
    )

    # Call the unified task to handle the show more functionality
    # Pass both the user_id and message_id so it can edit the message if possible
    unified_process_show_more.delay(
        user_id=callback_query.from_user.id,
        resource_url=resource_url,
        message_id=callback_query.message.message_id,
        platform="telegram"
    )


# Redirect to unified implementation
@celery_app.task(name='telegram_service.app.tasks.check_expiring_subscriptions')
def check_expiring_subscriptions():
    """
    Redirects to the unified check_expiring_subscriptions task.
    Kept for backward compatibility.
    """
    return unified_check_subscriptions.delay()


# Redirect to unified implementation
@celery_app.task(name='telegram_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """
    Redirects to the unified send_subscription_notification task.
    Kept for backward compatibility.
    """
    return unified_send_notification.delay(user_id, notification_type, data)