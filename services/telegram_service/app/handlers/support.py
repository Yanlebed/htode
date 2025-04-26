# services/telegram_service/app/handlers/support.py

import logging
from aiogram import types
from aiogram.dispatcher import FSMContext
from ..bot import dp, bot
from ..states.support_states import SupportStates
from ..keyboards import support_category_keyboard, support_redirect_keyboard, main_menu_keyboard
from common.messaging.handlers.support_handler import handle_support_command, handle_support_category

logger = logging.getLogger(__name__)


@dp.message_handler(lambda msg: msg.text == "🧑‍💻 Техпідтримка")
async def handle_support_command_telegram(message: types.Message, state: FSMContext):
    """
    Start the support conversation by asking the user to choose a category.
    Uses the unified support handler for cross-platform consistency.
    """
    # Set the state first since we have direct access to the state manager
    await SupportStates.waiting_for_category.set()

    # Use the unified handler for showing category options
    await handle_support_command(message.from_user.id, platform="telegram")


@dp.message_handler(lambda msg: msg.text in ["Оплата", "Технічні проблеми", "Інше"],
                    state=SupportStates.waiting_for_category)
async def process_support_category_telegram(message: types.Message, state: FSMContext):
    """
    Process the chosen support category.
    Uses the unified support handler for cross-platform consistency.
    """
    category = message.text

    # End the FSM as no further input is needed
    await state.finish()

    # Use the unified handler for category processing
    await handle_support_category(message.from_user.id, category, platform="telegram")


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