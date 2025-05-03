# services/telegram_service/app/handlers/support.py

from aiogram import types
from aiogram.dispatcher import FSMContext
from ..bot import dp
from ..states.support_states import SupportStates
from common.messaging.handlers.support_handler import handle_support_command, handle_support_category

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context


@dp.message_handler(lambda msg: msg.text == "🧑‍💻 Техпідтримка")
@log_operation("handle_support_command_telegram")
async def handle_support_command_telegram(message: types.Message, state: FSMContext):
    """
    Start the support conversation by asking the user to choose a category.
    Uses the unified support handler for cross-platform consistency.
    """
    user_id = message.from_user.id

    with log_context(logger, user_id=user_id, action="start_support"):
        # Set the state first since we have direct access to the state manager
        await SupportStates.waiting_for_category.set()

        # Use the unified handler for showing category options
        await handle_support_command(message.from_user.id, platform="telegram")
        logger.info("Support conversation started", extra={"user_id": user_id})


@dp.message_handler(lambda msg: msg.text in ["Оплата", "Технічні проблеми", "Інше"],
                    state=SupportStates.waiting_for_category)
@log_operation("process_support_category_telegram")
async def process_support_category_telegram(message: types.Message, state: FSMContext):
    """
    Process the chosen support category.
    Uses the unified support handler for cross-platform consistency.
    """
    user_id = message.from_user.id
    category = message.text

    with log_context(logger, user_id=user_id, category=category):
        # End the FSM as no further input is needed
        await state.finish()

        # Use the unified handler for category processing
        await handle_support_category(message.from_user.id, category, platform="telegram")
        logger.info("Support category processed", extra={
            "user_id": user_id,
            "category": category
        })


# Optional helper function for Telegram-specific support redirect functionality
def create_support_telegram_link(category: str) -> str:
    """
    Create a Telegram deep link for support redirection.

    Args:
        category: Support category (payment, technical, other)

    Returns:
        Deep link URL for Telegram
    """
    return f"https://t.me/bookly_beekly?start={category.lower()}"