# common/state_management.py

import logging
import json
import asyncio
from typing import Dict, Any, Optional, Union

from common.utils.cache import redis_client
from common.utils.retry_utils import retry_with_exponential_backoff, NETWORK_EXCEPTIONS

logger = logging.getLogger(__name__)


class UnifiedStateManager:
    """
    Unified state management for all messaging platforms.
    This provides a consistent interface for state management
    regardless of which platform (Telegram, Viber, WhatsApp) is being used.
    """

    def __init__(self, redis_prefix="user_state", ttl=86400):
        """
        Initialize the state manager.

        Args:
            redis_prefix: Prefix for Redis keys
            ttl: Default time-to-live for state data in seconds (default: 24 hours)
        """
        self.redis_prefix = redis_prefix
        self.default_ttl = ttl
        logger.info(f"Initialized UnifiedStateManager with prefix '{redis_prefix}'")

    def _get_key(self, platform: str, user_id: str) -> str:
        """
        Generate a Redis key for a user's state.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            user_id: User's platform-specific ID

        Returns:
            Formatted Redis key
        """
        return f"{self.redis_prefix}:{platform}:{user_id}"

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=0.5,
        retryable_exceptions=NETWORK_EXCEPTIONS
    )
    async def get_state(self, platform: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the state for a user.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            user_id: User's platform-specific ID

        Returns:
            User state dictionary or None if not found
        """
        key = self._get_key(platform, user_id)

        try:
            # Use asyncio to run the Redis get in a thread pool
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: redis_client.get(key))

            if data:
                return json.loads(data)
            return None
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in Redis for {platform} user {user_id}")
            return None
        except Exception as e:
            logger.error(f"Error getting state for {platform} user {user_id}: {e}")
            raise  # Let the retry decorator handle this

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=0.5,
        retryable_exceptions=NETWORK_EXCEPTIONS
    )
    async def set_state(self, platform: str, user_id: str, state: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Set the state for a user.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            user_id: User's platform-specific ID
            state: State dictionary to store
            ttl: Optional custom time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(platform, user_id)
        ttl = ttl or self.default_ttl

        try:
            serialized = json.dumps(state)

            # Use asyncio to run the Redis set in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: redis_client.setex(key, ttl, serialized)
            )
            return True
        except Exception as e:
            logger.error(f"Error setting state for {platform} user {user_id}: {e}")
            raise  # Let the retry decorator handle this

    async def update_state(self, platform: str, user_id: str, updates: Dict[str, Any],
                           ttl: Optional[int] = None) -> bool:
        """
        Update the state for a user (partial update).

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            user_id: User's platform-specific ID
            updates: Dictionary of state updates
            ttl: Optional custom time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        current_state = await self.get_state(platform, user_id) or {}
        current_state.update(updates)
        return await self.set_state(platform, user_id, current_state, ttl)

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=0.5,
        retryable_exceptions=NETWORK_EXCEPTIONS
    )
    async def clear_state(self, platform: str, user_id: str) -> bool:
        """
        Clear the state for a user.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            user_id: User's platform-specific ID

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(platform, user_id)

        try:
            # Use asyncio to run the Redis delete in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: redis_client.delete(key))
            return True
        except Exception as e:
            logger.error(f"Error clearing state for {platform} user {user_id}: {e}")
            raise  # Let the retry decorator handle this

    async def get_current_state_name(self, platform: str, user_id: str) -> Optional[str]:
        """
        Get the current state name for a user.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            user_id: User's platform-specific ID

        Returns:
            Current state name or None
        """
        state_data = await self.get_state(platform, user_id)
        return state_data.get('state') if state_data else None


# Create a singleton instance for global use
state_manager = UnifiedStateManager()