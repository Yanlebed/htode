# services/viber_service/app/flow_integration.py

import logging
import asyncio
from viberbot.api.messages import TextMessage
from .bot import viber, state_manager
from common.messaging.flow_builder import flow_library
from common.messaging.flow_integration_helper import (
    check_and_process_flow,
    process_flow_action,
    show_available_flows
)

logger = logging.getLogger(__name__)


async def handle_message_with_flow(user_id, message):
    """
    Handle an incoming Viber message with flow integration.
    Checks if a flow should handle the message first.

    Args:
        user_id: Viber user ID
        message: Viber message object
    """
    # Only handle text messages for flows
    if not isinstance(message, TextMessage):
        # For non-text messages, continue to normal processing
        from .handlers.basic_handlers import handle_message
        await handle_message(user_id, message)
        return

    text = message.text

    # Get current state for extra context
    state_data = await state_manager.get_state(user_id) or {}

    # Check if a flow should handle this message
    handled = await check_and_process_flow(
        user_id=user_id,
        platform="viber",
        message_text=text,
        extra_context=state_data
    )

    if handled:
        # Message was handled by a flow, no further processing needed
        return

    # If no flow handled the message, proceed with normal handling
    from .handlers.basic_handlers import handle_message
    await handle_message(user_id, message)


# Function to create a Viber keyboard for flows
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

    return {
        "Type": "keyboard",
        "Buttons": buttons
    }


# Function to handle flow commands
async def handle_flow_command(user_id, command):
    """
    Handle specific flow commands from Viber users

    Args:
        user_id: Viber user ID
        command: Command text

    Returns:
        True if handled, False otherwise
    """
    command_lower = command.lower().strip()

    # Handle special commands
    if command_lower in ["flows", "список потоків", "меню"]:
        await show_available_flows(user_id, "viber")
        return True

    if command_lower in ["search", "пошук", "нерухомість"]:
        await flow_library.start_flow("property_search", user_id, "viber")
        return True

    if command_lower in ["subscription", "підписка"]:
        await flow_library.start_flow("subscription", user_id, "viber")
        return True

    # Handle explicit flow actions
    if command_lower.startswith("flow:"):
        return await process_flow_action(user_id, "viber", command_lower)

    return False