# common/messaging/state_management.py

import logging
import json
from typing import Dict, Any, Optional, Union, Callable, Awaitable

from common.utils.cache import redis_client

logger = logging.getLogger(__name__)


class StateManager:
    """
    Unified state management wrapper for different platforms.
    Abstracts away platform-specific state management implementations.
    """

    def __init__(self, platform_handlers: Dict[str, Any] = None):
        """
        Initialize the state manager with platform-specific handlers.

        Args:
            platform_handlers: Dictionary mapping platform names to their state handlers
        """
        self.platform_handlers = platform_handlers or {}

    def register_platform_handler(self, platform: str, handler: Any) -> None:
        """
        Register a platform-specific handler.

        Args:
            platform: Platform name (telegram, viber, whatsapp)
            handler: Platform-specific state handler
        """
        self.platform_handlers[platform] = handler

    async def get_state(self, user_id: Union[str, int], platform: str) -> Optional[Dict[str, Any]]:
        """
        Get state for a user on a specific platform.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name

        Returns:
            Dictionary with state data or None
        """
        handler = self._get_handler(platform)
        if handler:
            # Use platform-specific handler
            try:
                return await handler.get_state(user_id)
            except Exception as e:
                logger.error(f"Error getting state via platform handler: {e}")

        # Fallback to direct Redis access
        return self._get_state_direct(f"{platform}:{user_id}")

    async def set_state(self, user_id: Union[str, int], platform: str, data: Dict[str, Any]) -> bool:
        """
        Set state for a user on a specific platform.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            data: State data to store

        Returns:
            True if successful, False otherwise
        """
        handler = self._get_handler(platform)
        if handler:
            # Use platform-specific handler
            try:
                return await handler.set_state(user_id, data)
            except Exception as e:
                logger.error(f"Error setting state via platform handler: {e}")

        # Fallback to direct Redis access
        return self._set_state_direct(f"{platform}:{user_id}", data)

    async def update_state(self, user_id: Union[str, int], platform: str, updates: Dict[str, Any]) -> bool:
        """
        Update state for a user on a specific platform.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            updates: State updates to apply

        Returns:
            True if successful, False otherwise
        """
        handler = self._get_handler(platform)
        if handler:
            # Use platform-specific handler
            try:
                return await handler.update_state(user_id, updates)
            except Exception as e:
                logger.error(f"Error updating state via platform handler: {e}")

        # Fallback to direct Redis access
        current_state = self._get_state_direct(f"{platform}:{user_id}") or {}
        current_state.update(updates)
        return self._set_state_direct(f"{platform}:{user_id}", current_state)

    async def clear_state(self, user_id: Union[str, int], platform: str) -> bool:
        """
        Clear state for a user on a specific platform.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name

        Returns:
            True if successful, False otherwise
        """
        handler = self._get_handler(platform)
        if handler:
            # Use platform-specific handler
            try:
                return await handler.clear_state(user_id)
            except Exception as e:
                logger.error(f"Error clearing state via platform handler: {e}")

        # Fallback to direct Redis access
        return self._clear_state_direct(f"{platform}:{user_id}")

    async def get_current_state_name(self, user_id: Union[str, int], platform: str) -> Optional[str]:
        """
        Get the current state name for a user.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name

        Returns:
            Current state name or None
        """
        state_data = await self.get_state(user_id, platform)
        return state_data.get('state') if state_data else None

    def _get_handler(self, platform: str) -> Any:
        """Get the handler for a specific platform."""
        return self.platform_handlers.get(platform)

    def _get_state_direct(self, key: str) -> Optional[Dict[str, Any]]:
        """Directly access Redis for state retrieval."""
        data = redis_client.get(f"state:{key}")
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in Redis for key state:{key}")
        return None

    def _set_state_direct(self, key: str, data: Dict[str, Any], ttl: int = 86400) -> bool:
        """Directly access Redis for state setting."""
        try:
            serialized = json.dumps(data)
            redis_client.setex(f"state:{key}", ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Error setting state for key state:{key}: {e}")
            return False

    def _clear_state_direct(self, key: str) -> bool:
        """Directly access Redis for state clearing."""
        try:
            redis_client.delete(f"state:{key}")
            return True
        except Exception as e:
            logger.error(f"Error clearing state for key state:{key}: {e}")
            return False


# Initialize a global instance
state_manager = StateManager()


class StateMachine:
    """
    Simple state machine for message handling flows across platforms.
    """

    def __init__(self, initial_state: str = "start"):
        """
        Initialize the state machine.

        Args:
            initial_state: Initial state name
        """
        self.handlers = {}
        self.initial_state = initial_state

    def add_state(self, state: str, handler: Callable[[Union[str, int], str, Dict[str, Any]], Awaitable[bool]]):
        """
        Add a state handler.

        Args:
            state: State name
            handler: Async function that processes this state
        """
        self.handlers[state] = handler

    async def process(self, user_id: Union[str, int], platform: str, message: str) -> bool:
        """
        Process a message based on the current state.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            message: User's message

        Returns:
            True if processed successfully, False otherwise
        """
        # Get current state
        current_state_name = await state_manager.get_current_state_name(user_id, platform)
        current_state_name = current_state_name or self.initial_state

        # Get state data
        state_data = await state_manager.get_state(user_id, platform) or {}

        # Find handler for current state
        handler = self.handlers.get(current_state_name)
        if not handler:
            logger.warning(f"No handler found for state {current_state_name}")
            return False

        # Execute the handler
        try:
            return await handler(user_id, platform, message, state_data)
        except Exception as e:
            logger.error(f"Error processing state {current_state_name}: {e}")
            return False