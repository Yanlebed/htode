# services/viber_service/app/flow_integration.py

from viberbot.api.messages import TextMessage
from .bot import state_manager
from common.messaging.unified_flow import flow_library
from common.messaging.unified_flow import (
    check_and_process_flow,
    process_flow_action,
    show_available_flows
)

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from . import logger


@log_operation("handle_message_with_flow")
async def handle_message_with_flow(user_id, message):
    """
    Handle an incoming Viber message with flow integration.
    Checks if a flow should handle the message first.

    Args:
        user_id: Viber user ID
        message: Viber message object
    """
    with log_context(logger, user_id=user_id, message_type=type(message).__name__):
        # Only handle text messages for flows
        if not isinstance(message, TextMessage):
            logger.debug(f"Non-text message received, forwarding to basic handler", extra={
                'user_id': user_id,
                'message_type': type(message).__name__
            })
            # For non-text messages, continue to normal processing
            from .handlers.basic_handlers import handle_message
            await handle_message(user_id, message)
            return

        text = message.text
        logger.info(f"Processing message with flow integration", extra={
            'user_id': user_id,
            'text_length': len(text)
        })

        # Get current state for extra context
        try:
            state_data = await state_manager.get_state(user_id) or {}
            logger.debug(f"Retrieved user state", extra={
                'user_id': user_id,
                'state': state_data.get('state', 'none')
            })
        except Exception as e:
            logger.error(f"Error retrieving user state", exc_info=True, extra={
                'user_id': user_id,
                'error_type': type(e).__name__
            })
            state_data = {}

        # Check if a flow should handle this message
        try:
            handled = await check_and_process_flow(
                user_id=user_id,
                platform="viber",
                message_text=text,
                extra_context=state_data
            )

            if handled:
                logger.info(f"Message handled by flow", extra={'user_id': user_id})
                # Message was handled by a flow, no further processing needed
                return
            else:
                logger.debug(f"Message not handled by flow, forwarding to basic handler", extra={
                    'user_id': user_id
                })
        except Exception as e:
            logger.error(f"Error in flow processing", exc_info=True, extra={
                'user_id': user_id,
                'error_type': type(e).__name__
            })

        # If no flow handled the message, proceed with normal handling
        from .handlers.basic_handlers import handle_message
        await handle_message(user_id, message)


@log_operation("create_flow_keyboard")
def create_flow_keyboard(flow_name: str, actions: list):
    """
    Create a Viber keyboard for flow operations.

    Args:
        flow_name: Name of the flow
        actions: List of action dictionaries with 'text' and 'action' keys
                (action can be 'start', 'end', or 'state_X')

    Returns:
        Viber keyboard dictionary
    """
    with log_context(logger, flow_name=flow_name, action_count=len(actions)):
        logger.debug(f"Creating flow keyboard", extra={
            'flow_name': flow_name,
            'num_actions': len(actions)
        })

        buttons = []

        for action_info in actions:
            text = action_info['text']
            action = action_info['action']

            # Create button with appropriate ActionBody
            buttons.append({
                "Columns": 6,
                "Rows": 1,
                "Text": text,
                "ActionType": "reply",
                "ActionBody": f"flow:{flow_name}:{action}"
            })

        keyboard = {
            "Type": "keyboard",
            "Buttons": buttons
        }

        logger.debug(f"Flow keyboard created", extra={
            'flow_name': flow_name,
            'num_buttons': len(buttons)
        })

        return keyboard


@log_operation("handle_flow_command")
async def handle_flow_command(user_id, command):
    """
    Handle specific flow commands from Viber users

    Args:
        user_id: Viber user ID
        command: Command text

    Returns:
        True if handled, False otherwise
    """
    with log_context(logger, user_id=user_id, command=command):
        command_lower = command.lower().strip()

        logger.debug(f"Processing flow command", extra={
            'user_id': user_id,
            'command': command_lower
        })

        try:
            # Handle special commands
            if command_lower in ["flows", "список потоків", "меню"]:
                await show_available_flows(user_id, "viber")
                logger.info(f"Showed available flows to user", extra={'user_id': user_id})
                return True

            if command_lower in ["search", "пошук", "нерухомість"]:
                await flow_library.start_flow("property_search", user_id, "viber")
                logger.info(f"Started property search flow", extra={'user_id': user_id})
                return True

            if command_lower in ["subscription", "підписка"]:
                await flow_library.start_flow("subscription", user_id, "viber")
                logger.info(f"Started subscription flow", extra={'user_id': user_id})
                return True

            # Handle explicit flow actions
            if command_lower.startswith("flow:"):
                result = await process_flow_action(user_id, "viber", command_lower)
                logger.info(f"Processed flow action", extra={
                    'user_id': user_id,
                    'command': command_lower,
                    'result': result
                })
                return result

            logger.debug(f"Command not recognized as flow command", extra={
                'user_id': user_id,
                'command': command_lower
            })
            return False

        except Exception as e:
            logger.error(f"Error handling flow command", exc_info=True, extra={
                'user_id': user_id,
                'command': command,
                'error_type': type(e).__name__
            })
            return False