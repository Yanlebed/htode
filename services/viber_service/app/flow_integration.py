# services/viber_service/app/flow_integration.py

import logging
import asyncio
from viberbot.api.messages import TextMessage
from .bot import viber, state_manager
from common.messaging.flow_builder import flow_library

logger = logging.getLogger(__name__)


async def check_and_process_flow(user_id: str, message_text: str) -> bool:
    """
    Check if there's an active flow for this user and process the message.

    Args:
        user_id: Viber user ID
        message_text: Message text

    Returns:
        True if the message was handled by a flow, False otherwise
    """
    # Try to process the message with the flow system
    if await flow_library.process_message(user_id, "viber", message_text):
        # Message was handled by a flow
        return True

    # Check for flow start commands
    for flow_name in flow_library.get_all_flows():
        # You can customize the command format as needed
        if message_text.lower() in [f"start_{flow_name}", f"flow_{flow_name}", flow_name]:
            # Start the flow for this user
            await flow_library.start_flow(flow_name, user_id, "viber")
            return True

    # Message wasn't handled by any flow
    return False


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

    # Check if a flow should handle this message
    if await check_and_process_flow(user_id, text):
        # Message was handled by a flow, no further processing needed
        return

    # If no flow handled the message, proceed with normal handling
    from .handlers.basic_handlers import handle_message
    await handle_message(user_id, message)


# Function to create flow-specific keyboard
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


# Function to process flow-specific actions from keyboard
async def process_flow_action(user_id: str, action_text: str):
    """
    Process a flow action from keyboard input.

    Args:
        user_id: Viber user ID
        action_text: Action text from button

    Returns:
        True if an action was processed, False otherwise
    """
    # Check if this is a flow action
    if not action_text.startswith("flow:"):
        return False

    # Parse the action
    parts = action_text.split(":", 2)
    if len(parts) != 3:
        return False

    _, flow_name, action = parts

    # Process the action
    if action == "start":
        # Start a flow
        return await flow_library.start_flow(flow_name, user_id, "viber")

    elif action.startswith("state_"):
        # Transition to a state in the active flow
        state_name = action[6:]  # Remove "state_" prefix
        return await flow_library.transition_active_flow(user_id, "viber", state_name)

    elif action == "end":
        # End the active flow
        return await flow_library.end_active_flow(user_id, "viber")

    # Unknown action
    return False