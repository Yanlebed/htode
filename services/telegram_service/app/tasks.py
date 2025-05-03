# services/telegram_service/app/tasks.py
from common.messaging.task_registry import register_platform_tasks
from aiogram.types import CallbackQuery

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context

# Register standard messaging tasks for Telegram
registered_tasks = register_platform_tasks(
    platform_name="telegram",
    task_module_path="telegram_service.app.tasks"
)

# Export the registered tasks for direct use
send_ad_with_extra_buttons = registered_tasks['send_ad_with_extra_buttons']
send_subscription_notification = registered_tasks['send_subscription_notification']

# Import the bot for the callback handler
from .bot import dp
from common.messaging.tasks import process_show_more_description

# This handler needs to remain in the Telegram service as it's tied to the callback query handler
@dp.callback_query_handler(lambda c: c.data.startswith("show_more:"))
@log_operation("show_more_description")
async def handle_show_more(callback_query: CallbackQuery):
    """
    Handle the show_more callback query and delegate to the unified task.
    This remains in the Telegram service as it's tied to the callback query handler.
    """
    with log_context(logger, user_id=callback_query.from_user.id, callback_data=callback_query.data):
        # Extract the resource_url from the callback data
        try:
            _, resource_url = callback_query.data.split("show_more:")
        except Exception as e:
            logger.warning("Invalid callback data format", extra={"error": str(e)})
            await callback_query.answer("Невірні дані.", show_alert=True)
            return

        # Acknowledge the callback query immediately
        await callback_query.answer("Отримання повного опису...")

        # Call the unified task to handle the show more functionality
        # Pass both the user_id and message_id so it can edit the message if possible
        process_show_more_description.delay(
            user_id=callback_query.from_user.id,
            resource_url=resource_url,
            message_id=callback_query.message.message_id,
            platform="telegram"
        )