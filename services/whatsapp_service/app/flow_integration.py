# services/whatsapp_service/app/flow_integration.py

import logging
import asyncio
from twilio.twiml.messaging_response import MessagingResponse
from .bot import sanitize_phone_number, get_user_state, update_user_state
from common.messaging.flow_builder import flow_library
from common.messaging.flow_integration_helper import (
    check_and_process_flow,
    process_flow_action,
    show_available_flows
)

logger = logging.getLogger(__name__)


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

    # Get current state for extra context
    state_data = await get_user_state(clean_user_id) or {}

    # Function to add immediate response if needed
    async def add_immediate_response():
        if response and not response.messages:
            # Add a processing message to the response if it's empty
            response.message("Processing your request...")

    # First, check if a flow should handle this message
    handled = await check_and_process_flow(
        user_id=clean_user_id,
        platform="whatsapp",
        message_text=text,
        extra_context=state_data,
        on_success=add_immediate_response
    )

    if handled:
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
    menu_text = f"Options for {flow_name}:\n\n"

    for i, action_info in enumerate(actions, 1):
        text = action_info['text']
        action = action_info['action']

        # Format as numbered menu
        menu_text += f"{i}. {text} (send \"{i}\" or \"flow:{flow_name}:{action}\")\n"

    menu_text += "\nSend the number or command to perform the action."
    return menu_text


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


# Handle specific flow commands for WhatsApp
async def handle_flow_command(user_id, command, response=None):
    """
    Handle specific flow commands for WhatsApp users

    Args:
        user_id: WhatsApp user ID
        command: Command text
        response: Optional Twilio response for immediate reply

    Returns:
        True if handled, False otherwise
    """
    command_lower = command.lower().strip()

    # Handle special commands
    if command_lower in ["flows", "menu", "options", "help"]:
        if response:
            response.message("Loading available options...")
        await show_available_flows(user_id, "whatsapp")
        return True

    if command_lower in ["search", "find", "property"]:
        if response:
            response.message("Starting property search...")
        await flow_library.start_flow("property_search", user_id, "whatsapp")
        return True

    if command_lower in ["subscription", "subscribe"]:
        if response:
            response.message("Loading subscription options...")
        await flow_library.start_flow("subscription", user_id, "whatsapp")
        return True

    # Handle explicit flow actions
    if command_lower.startswith("flow:"):
        return await process_flow_action(user_id, "whatsapp", command_lower)

    return False