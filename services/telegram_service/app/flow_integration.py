# services/telegram_service/app/flow_integration.py

import logging
from aiogram import types
from aiogram.dispatcher import FSMContext

from .bot import dp, bot
from common.messaging.unified_flow import flow_library
from common.messaging.unified_flow import (
    check_and_process_flow,
    process_flow_action,
    show_available_flows
)

logger = logging.getLogger(__name__)


@dp.message_handler(lambda message: True, state="*", priority=100)
async def flow_message_handler(message: types.Message, state: FSMContext = None):
    """
    Message handler that checks for active flows before letting other handlers process.
    This has a low priority (100) so specific command handlers will take precedence.
    """
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    # Get any state data for extra context
    state_data = {}
    if state:
        state_data = await state.get_data()

    # First check if an active flow wants to handle this message
    handled = await check_and_process_flow(
        user_id=user_id,
        platform="telegram",
        message_text=text,
        extra_context=state_data
    )

    if handled:
        # Message was handled by a flow, stop processing
        return


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("flow:"), state="*")
async def flow_callback_handler(callback_query: types.CallbackQuery, state: FSMContext = None):
    """
    Handler for flow-specific callbacks.
    """
    user_id = callback_query.from_user.id
    action_text = callback_query.data

    # Process the flow action
    if await process_flow_action(user_id, "telegram", action_text):
        await callback_query.answer("Action processed")
    else:
        await callback_query.answer("Invalid flow action")


# Command handler for starting property search
@dp.message_handler(commands=['search', 'find', 'property'])
async def start_property_search(message: types.Message):
    """
    Start the property search flow via command
    """
    user_id = message.from_user.id

    # Start the property search flow
    await flow_library.start_flow("property_search", user_id, "telegram")


# Command handler for starting subscription management
@dp.message_handler(commands=['subscribe', 'subscription'])
async def start_subscription_flow(message: types.Message):
    """
    Start the subscription management flow via command
    """
    user_id = message.from_user.id

    # Start the subscription flow
    await flow_library.start_flow("subscription", user_id, "telegram")


# Command handler for showing all available flows
@dp.message_handler(commands=['flows'])
async def show_flows_command(message: types.Message):
    """
    Show all available flows to the user
    """
    user_id = message.from_user.id

    await show_available_flows(user_id, "telegram")


# Function to create a Telegram inline keyboard for flows
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