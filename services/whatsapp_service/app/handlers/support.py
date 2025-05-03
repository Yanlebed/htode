# services/whatsapp_service/app/handlers/support.py

from ..bot import state_manager
from ..utils.message_utils import safe_send_message
from common.messaging.handlers.support_handler import handle_support_command, handle_support_category, \
    SUPPORT_CATEGORIES
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from .. import logger


@log_operation("handle_support_command_whatsapp")
async def handle_support_command_whatsapp(user_id, response=None):
    """
    Start the support conversation by asking the user to choose a category.
    Uses the unified support handler for cross-platform consistency.

    Args:
        user_id: WhatsApp user ID
        response: Optional Twilio response object for immediate reply
    """
    with log_context(logger, user_id=user_id):
        logger.info(f"Starting support conversation for user {user_id}")

        # Set state for WhatsApp
        await state_manager.update_state(user_id, {
            "state": "waiting_for_support_category"
        })

        logger.debug(f"Set state to waiting_for_support_category for user {user_id}")

        # Call the unified handler
        await handle_support_command(user_id, platform="whatsapp")


@log_operation("process_support_category_whatsapp")
async def process_support_category_whatsapp(user_id, text, response=None):
    """
    Process the chosen support category for WhatsApp users.
    Uses the unified support handler for cross-platform consistency.

    Args:
        user_id: WhatsApp user ID
        text: Message text (category selection)
        response: Optional Twilio response object for immediate reply
    """
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing support category selection for user {user_id}")

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
        logger.debug(f"Mapped input '{text}' to category '{category}' for user {user_id}")

        # Use the unified handler
        await handle_support_category(user_id, category, platform="whatsapp")


@log_operation("handle_copy_support")
async def handle_copy_support(user_id, data, response=None):
    """
    Handle the copy_support action for WhatsApp.
    Provides instructions on how to forward the message to support.

    Args:
        user_id: WhatsApp user ID
        data: Additional data like the category
        response: Optional Twilio response object for immediate reply
    """
    with log_context(logger, user_id=user_id, data=data):
        logger.info(f"Handling copy support action for user {user_id}")

        category = data.split(":")[1] if ":" in data else "other"
        support_phone = "+1234567890"  # Replace with your actual support WhatsApp number

        logger.debug(f"Support category: {category}, Support phone: {support_phone}")

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

        logger.info(f"Reset state to start for user {user_id}")


@log_operation("handle_support_flow")
async def handle_support_flow(user_id, text, user_state, response=None):
    """
    Handle support flow based on current user state.

    Args:
        user_id: WhatsApp user ID
        text: Message text
        user_state: Current user state
        response: Optional Twilio response object for immediate reply
    """
    with log_context(logger, user_id=user_id, user_state=user_state, user_input=text):
        logger.info(f"Processing support flow for user {user_id} in state {user_state}")

        if user_state == "waiting_for_support_category":
            logger.debug(f"Processing support category for user {user_id}")
            await process_support_category_whatsapp(user_id, text, response)
        elif text in ["🧑‍💻 Техпідтримка", "Техпідтримка", "support", "5"]:  # Accept multiple variants
            logger.debug(f"Starting support command for user {user_id}")
            await handle_support_command_whatsapp(user_id, response)
        elif text.startswith("copy_support:"):
            logger.debug(f"Handling copy support action for user {user_id}")
            await handle_copy_support(user_id, text, response)
        else:
            logger.warning(f"Unknown support flow command '{text}' for user {user_id}")