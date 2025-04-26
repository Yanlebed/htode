# common/messaging/flow_integration_helper.py

import logging
import asyncio
from typing import Dict, Any, Optional, Union, List, Callable

from common.messaging.flow_builder import flow_library, FlowContext
from common.messaging.unified_platform_utils import safe_send_menu

logger = logging.getLogger(__name__)

# Flow name mappings to recognize flow commands in different formats
FLOW_NAME_ALIASES = {
    # Property search flow
    "property_search": ["search", "пошук", "підписка", "subscription"],

    # Subscription flow (existing)
    "subscription": ["підписатися", "subscribe", "start_subscription"],

    # Phone verification flow
    "phone_verification": ["phone", "телефон", "верифікація", "verification"],

    # Support flow
    "support": ["допомога", "help", "підтримка", "техпідтримка", "support"]
}


async def check_and_process_flow(user_id: Union[str, int],
                                 platform: str,
                                 message_text: str,
                                 extra_context: Optional[Dict[str, Any]] = None,
                                 on_success: Optional[Callable] = None,
                                 on_failure: Optional[Callable] = None) -> bool:
    """
    Check if there's an active flow for this user and process the message,
    or check if the message is a flow command.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Platform identifier ("telegram", "viber", "whatsapp")
        message_text: Message text from user
        extra_context: Optional extra context data to include
        on_success: Optional callback function to call if message was handled
        on_failure: Optional callback function to call if message wasn't handled

    Returns:
        True if the message was handled by a flow, False otherwise
    """
    # First check if there's an active flow to handle this message
    if await flow_library.process_message(user_id, platform, message_text):
        logger.info(f"Message from {user_id} on {platform} handled by active flow")
        if on_success:
            await on_success()
        return True

    # Check if this is a command to start a flow
    flow_to_start = None

    # Convert message to lowercase for matching
    message_lower = message_text.lower().strip()

    # Check if message directly matches a flow name
    if message_lower in flow_library.get_all_flows():
        flow_to_start = message_lower
    else:
        # Check against aliases
        for flow_name, aliases in FLOW_NAME_ALIASES.items():
            if message_lower in aliases or any(alias in message_lower for alias in aliases):
                flow_to_start = flow_name
                break

    # If we found a flow to start, start it
    if flow_to_start:
        logger.info(f"Starting flow '{flow_to_start}' for {user_id} on {platform}")

        # Initialize flow data with any extra context
        initial_data = extra_context or {}

        # Start the flow
        if await flow_library.start_flow(flow_to_start, user_id, platform, initial_data):
            if on_success:
                await on_success()
            return True

    # If we get here, no flow handled the message
    if on_failure:
        await on_failure()
    return False


async def show_available_flows(user_id: Union[str, int], platform: str):
    """
    Show a menu of available flows the user can start.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Platform identifier ("telegram", "viber", "whatsapp")
    """
    # Get all registered flows
    all_flows = flow_library.get_all_flows()

    # Create menu options
    options = []

    # Add option for each flow with a human-readable name
    flow_display_names = {
        "property_search": "Пошук нерухомості",
        "subscription": "Керування підписками",
        "phone_verification": "Верифікація телефону",
        "support": "Технічна підтримка"
    }

    for flow_name in all_flows:
        display_name = flow_display_names.get(flow_name, flow_name.capitalize())
        options.append({
            "text": display_name,
            "value": f"flow:{flow_name}:start"
        })

    # Send the menu
    await safe_send_menu(
        user_id=user_id,
        text="Оберіть дію:",
        options=options,
        platform=platform
    )


async def process_flow_action(user_id: Union[str, int],
                              platform: str,
                              action_text: str) -> bool:
    """
    Process a flow action from a menu selection or explicit command.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Platform identifier ("telegram", "viber", "whatsapp")
        action_text: Action text (format: "flow:flow_name:action")

    Returns:
        True if action was processed, False otherwise
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
        return await flow_library.start_flow(flow_name, user_id, platform)
    elif action.startswith("state_"):
        # Transition to a state in the active flow
        state_name = action[6:]  # Remove "state_" prefix
        return await flow_library.transition_active_flow(user_id, platform, state_name)
    elif action == "end":
        # End the active flow
        return await flow_library.end_active_flow(user_id, platform)

    # Unknown action
    return False


async def create_flow_context(user_id: Union[str, int],
                              platform: str,
                              message: Optional[str] = None,
                              initial_data: Optional[Dict[str, Any]] = None) -> FlowContext:
    """
    Create a FlowContext object for custom flow handling.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Platform identifier ("telegram", "viber", "whatsapp")
        message: Optional message text
        initial_data: Optional initial flow data

    Returns:
        FlowContext object
    """
    from common.messaging.flow_builder import FlowContext

    # Get current state data if available
    from common.unified_state_management import state_manager
    state_data = await state_manager.get_state(user_id, platform) or {}
    flow_data = state_data.get("flow_data", {})

    # Merge with initial data if provided
    if initial_data:
        flow_data.update(initial_data)

    # Create and return context
    return FlowContext(user_id, platform, flow_data, message)