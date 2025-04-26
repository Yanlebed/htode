# services/viber_service/app/handlers/support.py

import logging
from ..bot import state_manager
from ..utils.message_utils import safe_send_message
from common.messaging.handlers.support_handler import handle_support_command, handle_support_category, \
    SUPPORT_CATEGORIES

logger = logging.getLogger(__name__)


async def handle_support_command_viber(user_id):
    """
    Start the support conversation by asking the user to choose a category.
    Uses the unified support handler for cross-platform consistency.
    """
    # Set state for Viber
    await state_manager.update_state(user_id, {
        "state": "waiting_for_support_category"
    })

    # Call the unified handler
    await handle_support_command(user_id, platform="viber")


async def process_support_category_viber(user_id, text):
    """
    Process the chosen support category for Viber users.
    Uses the unified support handler for cross-platform consistency.
    """
    # Map text input to category
    category_map = {
        "support_payment": "payment",
        "support_technical": "technical",
        "support_other": "other",
        "Оплата": "payment",
        "Технічні проблеми": "technical",
        "Інше": "other"
    }

    category = category_map.get(text, "other")

    # Use the unified handler
    await handle_support_category(user_id, category, platform="viber")


async def redirect_to_support(user_id, category):
    """
    Redirect the user to Viber support chat.

    Args:
        user_id: Viber user ID
        category: Support category for context
    """
    template = SUPPORT_CATEGORIES.get(category, SUPPORT_CATEGORIES['other'])['template']

    # Viber might not support deep linking like Telegram, so we provide instructions
    await safe_send_message(
        user_id,
        f"Відкрийте чат з нашою підтримкою та надішліть це повідомлення:\n\n{template}"
    )

    # Reset state
    await state_manager.update_state(user_id, {
        "state": "start"
    })


# This function would be called from the main message handler based on state
async def handle_support_flow(user_id, text, user_state):
    """
    Handle support flow based on current user state.

    Args:
        user_id: Viber user ID
        text: Message text
        user_state: Current user state
    """
    if user_state == "waiting_for_support_category":
        await process_support_category_viber(user_id, text)
    elif text == "🧑‍💻 Техпідтримка":
        await handle_support_command_viber(user_id)
    elif text.startswith("redirect_support:"):
        category = text.split(":")[1]
        await redirect_to_support(user_id, category)