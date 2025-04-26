# services/telegram_service/app/tasks.py
import logging
import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MediaGroup, CallbackQuery, WebAppInfo
from common.celery_app import celery_app
from .bot import bot, dp
from common.db.models import get_full_ad_description
from .utils.message_utils import (
    safe_answer_callback_query,
    delete_message_safe
)
from common.messaging.task_registry import register_platform_tasks
from common.messaging.tasks import process_show_more_description as unified_process_show_more

logger = logging.getLogger(__name__)

# Register standard messaging tasks for Telegram
registered_tasks = register_platform_tasks(
    platform_name="telegram",
    task_module_path="telegram_service.app.tasks"
)

# Access the registered tasks for direct use if needed
send_ad_with_extra_buttons = registered_tasks['send_ad_with_extra_buttons']
send_subscription_notification = registered_tasks['send_subscription_notification']
check_expiring_subscriptions = registered_tasks['check_expiring_subscriptions']

# This handler needs to remain in the Telegram service as it's tied to the callback query handler
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