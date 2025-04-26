# services/whatsapp_service/app/handlers/support.py

import logging
import asyncio
from ..bot import state_manager
from ..utils.message_utils import safe_send_message
from common.messaging.handlers.support_handler import handle_support_command, handle_support_category, \
    SUPPORT_CATEGORIES

logger = logging.getLogger(__name__)


async def handle_support_command_whatsapp(user_id, response=None):
    """
    Start the support conversation by asking the user to choose a category.
    Uses the unified support handler for cross-platform consistency.

    Args:
        user_id: WhatsApp user ID
        response: Optional Twilio response object for immediate reply
    """
    # Set state for WhatsApp
    await state_manager.update_state(user_id, {
        "state": "waiting_for_support_category"
    })

    # Call the unified handler
    await handle_support_command(user_id, platform="whatsapp")


async def process_support_category_whatsapp(user_id, text, response=None):
    """
    Process the chosen support category for WhatsApp users.
    Uses the unified support handler for cross-platform consistency.

    Args:
        user_id: WhatsApp user ID
        text: Message text (category selection)
        response: Optional Twilio response object for immediate reply
    """
    # Map numeric inputs and text to categories
    category_map = {
        "1": "payment",
        "2": "technical",
        "3": "other",
        "support_payment": "payment",
        "support_technical": "technical",
        "support_other": "other",
        "Оплата": "payment",
        "Технічні проблеми": "technical",
        "Інше": "other"
    }

    category = category_map.get(text, "other")

    # Use the unified handler
    await handle_support_category(user_id, category, platform="whatsapp")


async def handle_copy_support(user_id, data, response=None):
    """
    Handle the copy_support action for WhatsApp.
    Provides instructions on how to forward the message to support.

    Args:
        user_id: WhatsApp user ID
        data: Additional data like the category
        response: Optional Twilio response object for immediate reply
    """
    category = data.split(":")[1] if ":" in data else "other"
    support_phone = "+1234567890"  # Replace with your actual support WhatsApp number

    template = SUPPORT_CATEGORIES.get(category, SUPPORT_CATEGORIES['other'])['template']

    message = (
        f"Щоб зв'язатися з техпідтримкою:\n\n"
        f"1. Додайте номер {support_phone} до контактів\n"
        f"2. Відкрийте WhatsApp чат з цим номером\n"
        f"3. Скопіюйте та надішліть наступне повідомлення:\n\n"
        f"{template}"
    )

    if response:
        response.message(message)
    else:
        await safe_send_message(user_id, message)

    # Reset state
    await state_manager.update_state(user_id, {
        "state": "start"
    })


# This function would be called from the main message handler based on state
async def handle_support_flow(user_id, text, user_state, response=None):
    """
    Handle support flow based on current user state.

    Args:
        user_id: WhatsApp user ID
        text: Message text
        user_state: Current user state
        response: Optional Twilio response object for immediate reply
    """
    if user_state == "waiting_for_support_category":
        await process_support_category_whatsapp(user_id, text, response)
    elif text in ["🧑‍💻 Техпідтримка", "Техпідтримка", "support", "5"]:  # Accept multiple variants
        await handle_support_command_whatsapp(user_id, response)
    elif text.startswith("copy_support:"):
        await handle_copy_support(user_id, text, response)