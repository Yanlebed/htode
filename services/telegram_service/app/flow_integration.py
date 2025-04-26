# services/telegram_service/app/flow_integration.py

import logging
from aiogram import types
from aiogram.dispatcher import FSMContext

from .bot import dp, bot
from common.messaging.flow_builder import flow_library

logger = logging.getLogger(__name__)


async def check_and_process_flow(message: types.Message, state: FSMContext = None) -> bool:
    """
    Check if there's an active flow for this user and process the message.

    Args:
        message: Telegram message object
        state: Optional FSMContext for Telegram FSM integration

    Returns:
        True if the message was handled by a flow, False otherwise
    """
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    # Try to process the message with the flow system
    if await flow_library.process_message(user_id, "telegram", text):
        # Message was handled by a flow
        return True

    # Check for flow start commands
    for flow_name in flow_library.get_all_flows():
        # You can customize the command format as needed
        if text.lower() in [f"/start_{flow_name}", f"/{flow_name}", f"start_{flow_name}"]:
            # Start the flow for this user
            await flow_library.start_flow(flow_name, user_id, "telegram")
            return True

    # Message wasn't handled by any flow
    return False


# Register a catch-all handler with low priority to check for flows
@dp.message_handler(lambda message: True, state="*", priority=100)
async def flow_message_handler(message: types.Message, state: FSMContext = None):
    """
    Message handler that checks for active flows before letting other handlers process.
    This has a low priority (100) so specific command handlers will take precedence.
    """
    # First check if an active flow wants to handle this message
    if await check_and_process_flow(message, state):
        # Message was handled by a flow, stop processing
        return

    # If no flow handled the message, it will fall through to other handlers


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("flow:"), state="*")
async def flow_callback_handler(callback_query: types.CallbackQuery, state: FSMContext = None):
    """
    Handler for flow-specific callbacks.
    """
    # Extract flow information from callback data
    parts = callback_query.data.split(":", 2)
    if len(parts) < 3:
        # Invalid format
        await callback_query.answer("Invalid flow callback")
        return

    _, flow_name, action = parts
    user_id = callback_query.from_user.id

    if action == "start":
        # Start a flow
        started = await flow_library.start_flow(flow_name, user_id, "telegram")
        if started:
            await callback_query.answer(f"Started {flow_name}")
        else:
            await callback_query.answer(f"Couldn't start {flow_name}")

    elif action.startswith("state_"):
        # Transition to a state in the active flow
        state_name = action[6:]  # Remove "state_" prefix
        transitioned = await flow_library.transition_active_flow(user_id, "telegram", state_name)
        if transitioned:
            await callback_query.answer(f"Moved to {state_name}")
        else:
            await callback_query.answer("Couldn't transition")

    elif action == "end":
        # End the active flow
        ended = await flow_library.end_active_flow(user_id, "telegram")
        if ended:
            await callback_query.answer("Flow ended")
        else:
            await callback_query.answer("No active flow to end")

    else:
        # Unknown action
        await callback_query.answer("Unknown flow action")


# Add a function to create flow-compatible keyboards
def create_flow_keyboard(flow_name: str, actions: list):
    """
    Create an inline keyboard for flow operations.

    Args:
        flow_name: Name of the flow
        actions: List of action dictionaries with 'text' and 'action' keys
                (action can be 'start', 'end', or 'state_X')

    Returns:
        InlineKeyboardMarkup
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    for action_info in actions:
        text = action_info['text']
        action = action_info['action']

        # Create button with appropriate callback data
        keyboard.insert(
            types.InlineKeyboardButton(
                text=text,
                callback_data=f"flow:{flow_name}:{action}"
            )
        )

    return keyboard