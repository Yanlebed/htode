# common/messaging/flow_builder.py

import logging
from typing import Dict, Any, Optional, Union, Callable, List, Set, Type

from common.messaging.utils import safe_send_message, safe_send_menu
from common.messaging.state_management import state_manager

logger = logging.getLogger(__name__)


class MessageFlow:
    """
    A platform-agnostic message flow builder.
    Makes it easy to create consistent conversation flows across platforms.
    """

    def __init__(self, name: str, initial_state: str = "start"):
        """
        Initialize a message flow.

        Args:
            name: Name of the flow
            initial_state: Initial state name
        """
        self.name = name
        self.initial_state = initial_state
        self.states = {}
        self.transitions = {}
        self.global_handlers = {}

    def add_state(self, state_name: str, handler: Optional[Callable] = None, **kwargs):
        """
        Add a state to the flow.

        Args:
            state_name: Name of the state
            handler: Optional handler function for this state
            **kwargs: Additional state metadata
        """
        self.states[state_name] = {
            "handler": handler,
            **kwargs
        }
        return self

    def add_transition(self, from_state: str, to_state: str, condition: Optional[Callable] = None, **kwargs):
        """
        Add a transition between states.

        Args:
            from_state: Source state name
            to_state: Target state name
            condition: Optional function that returns True if transition should occur
            **kwargs: Additional transition metadata
        """
        if from_state not in self.transitions:
            self.transitions[from_state] = []

        self.transitions[from_state].append({
            "to_state": to_state,
            "condition": condition,
            **kwargs
        })
        return self

    def add_global_handler(self, handler_name: str, handler: Callable):
        """
        Add a global handler that is available in all states.

        Args:
            handler_name: Name of the handler
            handler: Handler function
        """
        self.global_handlers[handler_name] = handler
        return self

    async def start(self, user_id: Union[str, int], platform: str):
        """
        Start the flow for a user.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
        """
        # Update user state
        await state_manager.update_state(user_id, platform, {
            "state": self.initial_state,
            "active_flow": self.name,
            "flow_data": {}
        })

        # Execute initial state handler if available
        initial_state_data = self.states.get(self.initial_state)
        if initial_state_data and initial_state_data.get("handler"):
            await initial_state_data["handler"](user_id, platform)

    async def process_message(self, user_id: Union[str, int], platform: str, message: str):
        """
        Process a message within the flow.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            message: User's message

        Returns:
            True if the message was handled, False otherwise
        """
        # Get current state
        state_data = await state_manager.get_state(user_id, platform) or {}
        current_state = state_data.get("state", self.initial_state)
        flow_data = state_data.get("flow_data", {})

        # Check for global handlers first
        for handler_name, handler in self.global_handlers.items():
            if await handler(user_id, platform, message, current_state, flow_data):
                return True

        # Check state-specific handler
        state_info = self.states.get(current_state)
        if state_info and state_info.get("handler"):
            handler = state_info["handler"]
            result = await handler(user_id, platform, message, flow_data)

            # Update flow data
            if isinstance(result, dict):
                # Handler returned new flow data
                flow_data.update(result)
                await state_manager.update_state(user_id, platform, {
                    "flow_data": flow_data
                })

            # Check for transitions
            await self._check_transitions(user_id, platform, current_state, message, flow_data)

            return True

        # No handler for this state
        logger.warning(f"No handler for state {current_state} in flow {self.name}")
        return False

    async def transition_to(self, user_id: Union[str, int], platform: str, target_state: str):
        """
        Manually transition to a specific state.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            target_state: Target state name
        """
        # Update state
        await state_manager.update_state(user_id, platform, {
            "state": target_state
        })

        # Execute new state handler
        state_info = self.states.get(target_state)
        if state_info and state_info.get("handler"):
            state_data = await state_manager.get_state(user_id, platform) or {}
            flow_data = state_data.get("flow_data", {})
            await state_info["handler"](user_id, platform, None, flow_data)

    async def end(self, user_id: Union[str, int], platform: str):
        """
        End the flow for a user.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
        """
        # Clear flow state
        await state_manager.update_state(user_id, platform, {
            "state": "start",
            "active_flow": None,
            "flow_data": {}
        })

    async def _check_transitions(self, user_id: Union[str, int], platform: str,
                                 current_state: str, message: str, flow_data: Dict[str, Any]):
        """
        Check if any transitions should be triggered.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            current_state: Current state name
            message: User's message
            flow_data: Flow data dictionary
        """
        transitions = self.transitions.get(current_state, [])

        for transition in transitions:
            condition = transition.get("condition")

            # Check if condition is met
            if condition is None or await condition(message, flow_data):
                target_state = transition["to_state"]

                # Update state
                await state_manager.update_state(user_id, platform, {
                    "state": target_state
                })

                # Execute new state handler
                target_state_info = self.states.get(target_state)
                if target_state_info and target_state_info.get("handler"):
                    await target_state_info["handler"](user_id, platform, message, flow_data)

                # Only apply the first matching transition
                break


class FlowLibrary:
    """
    A library of reusable message flows.
    """

    def __init__(self):
        """Initialize the flow library."""
        self.flows = {}

    def register_flow(self, flow: MessageFlow):
        """
        Register a flow in the library.

        Args:
            flow: MessageFlow instance
        """
        self.flows[flow.name] = flow
        return self

    def get_flow(self, name: str) -> Optional[MessageFlow]:
        """
        Get a flow by name.

        Args:
            name: Flow name

        Returns:
            MessageFlow instance or None
        """
        return self.flows.get(name)

    def start_flow(self, name: str, user_id: Union[str, int], platform: str):
        """
        Start a flow for a user.

        Args:
            name: Flow name
            user_id: User's platform-specific ID
            platform: Platform name

        Returns:
            True if flow was started, False otherwise
        """
        flow = self.get_flow(name)
        if not flow:
            logger.warning(f"Flow {name} not found")
            return False

        await flow.start(user_id, platform)
        return True

    def process_message_in_flow(self, name: str, user_id: Union[str, int], platform: str, message: str):
        """
        Process a message in a specific flow.

        Args:
            name: Flow name
            user_id: User's platform-specific ID
            platform: Platform name
            message: User's message

        Returns:
            True if message was processed, False otherwise
        """
        flow = self.get_flow(name)
        if not flow:
            logger.warning(f"Flow {name} not found")
            return False

        return await flow.process_message(user_id, platform, message)


# Create a global instance
flow_library = FlowLibrary()

# Define some common flows

# Support flow
support_flow = MessageFlow("support", "waiting_for_category")


async def show_support_categories(user_id, platform, message=None, flow_data=None):
    """Show support categories."""
    from common.messaging.handlers.support_handler import handle_support_command
    return await handle_support_command(user_id, platform)


async def process_category_selection(user_id, platform, message, flow_data):
    """Process the selected support category."""
    from common.messaging.handlers.support_handler import handle_support_category

    # Map common category names
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

    category = category_map.get(message, "other")
    await handle_support_category(user_id, category, platform)
    return {"category": category}


support_flow.add_state("waiting_for_category", show_support_categories)
support_flow.add_state("processing_category", process_category_selection)
support_flow.add_transition("waiting_for_category", "processing_category",
                            lambda msg, data: msg in ["1", "2", "3", "Оплата", "Технічні проблеми", "Інше"])

# Register common flows
flow_library.register_flow(support_flow)

# Phone verification flow
phone_flow = MessageFlow("phone_verification", "waiting_for_phone")


async def request_phone(user_id, platform, message=None, flow_data=None):
    """Request phone number."""
    await safe_send_message(
        user_id=user_id,
        text="Для додавання номера телефону і єдиного входу з різних пристроїв, "
             "будь ласка, введіть свій номер телефону в міжнародному форматі, "
             "наприклад +380991234567",
        platform=platform
    )


async def process_phone(user_id, platform, message, flow_data):
    """Process phone number."""
    from common.verification.phone_service import create_verification_code

    # Clean the phone number
    phone_number = ''.join(c for c in message if c.isdigit() or c == '+')
    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number

    # Generate code
    code = create_verification_code(phone_number)

    # Send code instructions
    await safe_send_message(
        user_id=user_id,
        text=f"Код