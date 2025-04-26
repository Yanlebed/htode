# services/whatsapp_service/app/flow_integration.py

import logging
import asyncio
from twilio.twiml.messaging_response import MessagingResponse
from .bot import sanitize_phone_number, state_manager
from common.messaging.flow_builder import flow_library

logger = logging.getLogger(__name__)


async def check_and_process_flow(user_id: str, message_text: str, response: MessagingResponse = None) -> bool:
    """
    Check if there's an active flow for this user and process the message.

    Args:
        user_id: WhatsApp user ID (sanitized phone number)
        message_text: Message text
        response: Optional Twilio MessagingResponse for immediate response

    Returns:
        True if the message was handled by a flow, False otherwise
    """
    # Try to process the message with the flow system
    if await flow_library.process_message(user_id, "whatsapp", message_text):
        # Message was handled by a flow
        return True

    # Check for flow start commands
    for flow_name in flow_library.get_all_flows():
        # You can customize the command format as needed
        if message_text.lower() in [f"start_{flow_name}", f"flow_{flow_name}", flow_name]:
            # Start the flow for this user
            await flow_library.start_flow(flow_name, user_id, "whatsapp")
            return True

    # Message wasn't handled by any flow
    return False


async def handle_message_with_flow(user_id: str, text: str, media_urls=None, response=None):
    """
    Handle an incoming WhatsApp message with flow integration.

    Args:
        user_id: WhatsApp user ID (sanitized phone number)
        text: Message text
        media_urls: Optional list of media URLs
        response: Optional Twilio MessagingResponse for immediate response
    """
    # Clean the phone number to use as user ID
    clean_user_id = sanitize_phone_number(user_id)

    # First, check if a flow should handle this message
    if await check_and_process_flow(clean_user_id, text, response):
        # Message was handled by a flow, no further processing needed
        return

    # If no flow handled the message, proceed with normal handling
    from .handlers.basic_handlers import handle_message
    await handle_message(clean_user_id, text, media_urls, response)


# Function to create text-based "menu" for flows
def create_flow_menu(flow_name: str, actions: list) -> str:
    """
    Create a text-based menu for flow operations, since WhatsApp
    doesn't support rich keyboards like Telegram or Viber.

    Args:
        flow_name: Name of the flow
        actions: List of action dictionaries with 'text' and 'action' keys
                (action can be 'start', 'end', or 'state_X')

    Returns:
        Formatted text menu
    """
    menu_text = f"Flow Options for {flow_name}:\n\n"

    for i, action_info in enumerate(actions, 1):
        text = action_info['text']
        action = action_info['action']

        # Format as numbered menu
        menu_text += f"{i}. {text} (send \"flow:{flow_name}:{action}\")\n"

    menu_text += "\nSend the command in parentheses to perform the action."
    return menu_text


# Function to process flow-specific actions
async def process_flow_action(user_id: str, action_text: str) -> bool:
    """
    Process a flow action from text input.

    Args:
        user_id: WhatsApp user ID
        action_text: Action text command

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
        return await flow_library.start_flow(flow_name, user_id, "whatsapp")

    elif action.startswith("state_"):
        # Transition to a state in the active flow
        state_name = action[6:]  # Remove "state_" prefix
        return await flow_library.transition_active_flow(user_id, "whatsapp", state_name)

    elif action == "end":
        # End the active flow
        return await flow_library.end_active_flow(user_id, "whatsapp")

    # Unknown action
    return False


# Function to handle numeric menu selections for flows
async def process_numeric_flow_action(user_id: str, text: str, state_data: dict) -> bool:
    """
    Process numeric menu selections for flow navigation.
    This allows users to select options by number instead of typing the whole command.

    Args:
        user_id: WhatsApp user ID
        text: Message text (should be a number)
        state_data: User state data

    Returns:
        True if a numeric action was processed, False otherwise
    """
    # Check if this is a number and we have flow menu options
    if not text.isdigit() or 'flow_menu_options' not in state_data:
        return False

    option_index = int(text) - 1
    options = state_data['flow_menu_options']

    # Check if the option index is valid
    if option_index < 0 or option_index >= len(options):
        return False

    # Get the selected option
    selected_option = options[option_index]
    flow_name = selected_option.get('flow_name')
    action = selected_option.get('action')

    if not flow_name or not action:
        return False

    # Process the action
    if action == "start":
        # Start a flow
        return await flow_library.start_flow(flow_name, user_id, "whatsapp")

    elif action.startswith("state_"):
        # Transition to a state in the active flow
        state_name = action[6:]  # Remove "state_" prefix
        return await flow_library.transition_active_flow(user_id, "whatsapp", state_name)

    elif action == "end":
        # End the active flow
        return await flow_library.end_active_flow(user_id, "whatsapp")

    # Unknown action
    return False