# common/messaging/platform_router.py

import logging
import importlib
import inspect
from typing import Dict, Any, Optional, Union, Callable, List, Tuple, Type

from common.messaging.unified_interface import MessagingInterface
from common.messaging.unified_platform_utils import resolve_user_id

logger = logging.getLogger(__name__)


class PlatformRouter:
    """
    A router that dynamically loads platform-specific handlers and routes messages to them.
    """

    def __init__(self):
        """Initialize the platform router."""
        self.messengers = {}
        self.handlers = {}
        self.flows = {}

    def register_messenger(self, platform: str, messenger_class: Type[MessagingInterface]) -> None:
        """
        Register a messenger implementation for a platform.

        Args:
            platform: Platform name (telegram, viber, whatsapp)
            messenger_class: MessagingInterface implementation class
        """
        try:
            # Get the messenger instance
            if platform == "telegram":
                from services.telegram_service.app.bot import bot
                messenger = messenger_class(bot)
            elif platform == "viber":
                from services.viber_service.app.bot import viber
                messenger = messenger_class(viber)
            elif platform == "whatsapp":
                from services.whatsapp_service.app.bot import client
                messenger = messenger_class(client)
            else:
                logger.error(f"Unknown platform: {platform}")
                return

            self.messengers[platform] = messenger
            logger.info(f"Registered messenger for platform: {platform}")
        except ImportError as e:
            logger.error(f"Failed to import dependencies for platform {platform}: {e}")
        except Exception as e:
            logger.error(f"Failed to register messenger for platform {platform}: {e}")

    def register_handler(self, platform: str, handler_name: str, handler_func: Callable) -> None:
        """
        Register a handler function for a specific platform.

        Args:
            platform: Platform name
            handler_name: Name of the handler
            handler_func: Handler function
        """
        if platform not in self.handlers:
            self.handlers[platform] = {}

        self.handlers[platform][handler_name] = handler_func
        logger.info(f"Registered handler '{handler_name}' for platform: {platform}")

    def register_flow(self, flow_name: str, flow_handlers: Dict[str, Dict[str, Callable]]) -> None:
        """
        Register a message flow that can work across platforms.

        Args:
            flow_name: Name of the flow
            flow_handlers: Dictionary mapping states to handlers for each platform
                           Format: {state_name: {platform_name: handler_func}}
        """
        self.flows[flow_name] = flow_handlers
        logger.info(f"Registered flow '{flow_name}'")

    def get_messenger(self, platform: str) -> Optional[MessagingInterface]:
        """
        Get the messenger for a specific platform.

        Args:
            platform: Platform name

        Returns:
            MessagingInterface implementation or None
        """
        return self.messengers.get(platform)

    def get_handler(self, platform: str, handler_name: str) -> Optional[Callable]:
        """
        Get a handler function for a specific platform.

        Args:
            platform: Platform name
            handler_name: Name of the handler

        Returns:
            Handler function or None
        """
        return self.handlers.get(platform, {}).get(handler_name)

    def get_flow_handler(self, flow_name: str, state_name: str, platform: str) -> Optional[Callable]:
        """
        Get a handler function for a specific state in a flow.

        Args:
            flow_name: Name of the flow
            state_name: Name of the state
            platform: Platform name

        Returns:
            Handler function or None
        """
        flow = self.flows.get(flow_name)
        if not flow:
            return None

        state_handlers = flow.get(state_name)
        if not state_handlers:
            return None

        return state_handlers.get(platform)

    async def route_message(self, user_id: Union[str, int], message: str,
                            platform: str = None, context: Dict[str, Any] = None) -> Any:
        """
        Route a message to the appropriate handler.

        Args:
            user_id: User's platform-specific ID or database ID
            message: Message text
            platform: Optional platform override
            context: Optional context data

        Returns:
            Result from the handler
        """
        try:
            # Resolve user ID and platform
            db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)
            platform = platform_name or platform or "telegram"  # Default to telegram

            # Get the user's current state
            from common.unified_state_management import state_manager
            state_data = await state_manager.get_state(user_id, platform) or {}
            current_state = state_data.get("state", "start")

            # Check for global commands (like /start, /help, etc.)
            command_handler = self._get_command_handler(message, platform)
            if command_handler:
                return await command_handler(platform_id or user_id, message, context or {})

            # Check for active flow
            active_flow = state_data.get("active_flow")
            if active_flow:
                flow_handler = self.get_flow_handler(active_flow, current_state, platform)
                if flow_handler:
                    return await flow_handler(platform_id or user_id, message, state_data)

            # Check for state-specific handler
            state_handler_name = f"handle_state_{current_state}"
            state_handler = self.get_handler(platform, state_handler_name)
            if state_handler:
                return await state_handler(platform_id or user_id, message, state_data)

            # Fall back to default handler
            default_handler = self.get_handler(platform, "handle_default")
            if default_handler:
                return await default_handler(platform_id or user_id, message, state_data)

            logger.warning(f"No handler found for message in platform {platform}, state {current_state}")
            return None
        except Exception as e:
            logger.error(f"Error routing message: {e}")
            return None

    def _get_command_handler(self, message: str, platform: str) -> Optional[Callable]:
        """
        Check if a message is a command and get the appropriate handler.

        Args:
            message: Message text
            platform: Platform name

        Returns:
            Command handler function or None
        """
        if not message:
            return None

        # Check for commands
        if message.startswith('/'):
            command = message[1:].split()[0].lower()
            handler_name = f"handle_command_{command}"
            return self.get_handler(platform, handler_name)

        return None

    @classmethod
    def create_and_configure(cls) -> 'PlatformRouter':
        """
        Create and configure a PlatformRouter with all available platforms and handlers.

        Returns:
            Configured PlatformRouter instance
        """
        router = cls()

        # Register messengers
        try:
            from common.messaging.telegram_messaging import TelegramMessaging
            router.register_messenger("telegram", TelegramMessaging)
        except ImportError:
            logger.warning("TelegramMessaging not found or could not be imported")

        try:
            from common.messaging.viber_messaging import ViberMessaging
            router.register_messenger("viber", ViberMessaging)
        except ImportError:
            logger.warning("ViberMessaging not found or could not be imported")

        try:
            from common.messaging.whatsapp_messaging import WhatsAppMessaging
            router.register_messenger("whatsapp", WhatsAppMessaging)
        except ImportError:
            logger.warning("WhatsAppMessaging not found or could not be imported")

        # Auto-load handlers from platform-specific modules
        platforms = ["telegram", "viber", "whatsapp"]
        handler_modules = [
            "services.{}_service.app.handlers.basic_handlers",
            "services.{}_service.app.handlers.advanced_handlers",
            "services.{}_service.app.handlers.subscription",
            "services.{}_service.app.handlers.support",
            "services.{}_service.app.handlers.favorites",
            "services.{}_service.app.handlers.payment",
            "services.{}_service.app.handlers.phone_verification"
        ]

        for platform in platforms:
            for module_template in handler_modules:
                module_name = module_template.format(platform)
                try:
                    module = importlib.import_module(module_name)

                    # Find handler functions (async functions that start with "handle_")
                    for name, obj in inspect.getmembers(module):
                        if (name.startswith("handle_") and inspect.iscoroutinefunction(obj)):
                            router.register_handler(platform, name, obj)
                except ImportError:
                    # Module doesn't exist for this platform, skip
                    pass
                except Exception as e:
                    logger.error(f"Error loading handlers from {module_name}: {e}")

        return router


# Create a global instance
platform_router = PlatformRouter.create_and_configure()