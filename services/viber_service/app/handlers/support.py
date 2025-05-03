# services/viber_service/app/handlers/support.py

from ..bot import state_manager
from ..utils.message_utils import safe_send_message
from common.messaging.handlers.support_handler import handle_support_command, handle_support_category, \
    SUPPORT_CATEGORIES

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from .. import logger


@log_operation("handle_support_command_viber")
async def handle_support_command_viber(user_id):
    """
    Start the support conversation by asking the user to choose a category.
    Uses the unified support handler for cross-platform consistency.
    """
    with log_context(logger, user_id=user_id, command="support"):
        # Set state for Viber
        await state_manager.update_state(user_id, {
            "state": "waiting_for_support_category"
        })

        logger.info(f"Starting support flow for user {user_id}")

        # Call the unified handler
        try:
            await handle_support_command(user_id, platform="viber")
            logger.info(f"Support command handled successfully for user {user_id}")
        except Exception as e:
            logger.error(f"Error handling support command", exc_info=True, extra={
                'user_id': user_id,
                'error_type': type(e).__name__
            })
            raise


@log_operation("process_support_category_viber")
async def process_support_category_viber(user_id, text):
    """
    Process the chosen support category for Viber users.
    Uses the unified support handler for cross-platform consistency.
    """
    with log_context(logger, user_id=user_id, category_text=text):
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

        logger.info(f"Processing support category for user {user_id}", extra={
            'raw_text': text,
            'mapped_category': category
        })

        # Use the unified handler
        try:
            await handle_support_category(user_id, category, platform="viber")
            logger.info(f"Support category processed successfully", extra={
                'user_id': user_id,
                'category': category
            })
        except Exception as e:
            logger.error(f"Error processing support category", exc_info=True, extra={
                'user_id': user_id,
                'category': category,
                'error_type': type(e).__name__
            })
            raise


@log_operation("redirect_to_support")
async def redirect_to_support(user_id, category):
    """
    Redirect the user to Viber support chat.

    Args:
        user_id: Viber user ID
        category: Support category for context
    """
    with log_context(logger, user_id=user_id, support_category=category):
        template = SUPPORT_CATEGORIES.get(category, SUPPORT_CATEGORIES['other'])['template']

        logger.info(f"Redirecting user to support", extra={
            'user_id': user_id,
            'category': category,
            'template_length': len(template)
        })

        # Viber might not support deep linking like Telegram, so we provide instructions
        await safe_send_message(
            user_id,
            f"Відкрийте чат з нашою підтримкою та надішліть це повідомлення:\n\n{template}"
        )

        # Reset state
        await state_manager.update_state(user_id, {
            "state": "start"
        })

        logger.info(f"Support redirect completed for user {user_id}")


@log_operation("handle_support_flow")
async def handle_support_flow(user_id, text, user_state):
    """
    Handle support flow based on current user state.

    Args:
        user_id: Viber user ID
        text: Message text
        user_state: Current user state
    """
    with log_context(logger, user_id=user_id, state=user_state, message_text=text):
        logger.debug(f"Handling support flow for user {user_id}", extra={
            'current_state': user_state,
            'message_length': len(text) if text else 0
        })

        try:
            if user_state == "waiting_for_support_category":
                await process_support_category_viber(user_id, text)
                logger.info(f"Processed support category selection for user {user_id}")
            elif text == "🧑‍💻 Техпідтримка":
                await handle_support_command_viber(user_id)
                logger.info(f"Initiated support command for user {user_id}")
            elif text.startswith("redirect_support:"):
                category = text.split(":")[1]
                await redirect_to_support(user_id, category)
                logger.info(f"Redirected to support with category", extra={
                    'user_id': user_id,
                    'category': category
                })
            else:
                logger.warning(f"Unhandled support flow state", extra={
                    'user_id': user_id,
                    'state': user_state,
                    'text': text
                })
        except Exception as e:
            logger.error(f"Error in support flow", exc_info=True, extra={
                'user_id': user_id,
                'state': user_state,
                'error_type': type(e).__name__
            })
            # Re-raise the exception after logging
            raise