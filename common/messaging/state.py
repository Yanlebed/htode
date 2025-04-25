# common/messaging/state.py

import json
import logging
import asyncio
from typing import Dict, Any, Optional, Union, Type

import redis

logger = logging.getLogger(__name__)


class PlatformStateManager:
    """
    Enhanced state manager for platform-specific user states.
    Extends the original RedisStateManager with platform-specific features.
    """

    def __init__(self, platform: str, redis_url: Optional[str] = None, ttl: int = 86400):
        """
        Initialize the state manager for a specific platform.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            redis_url: Optional Redis URL (uses REDIS_URL env var if not provided)
            ttl: Default time-to-live for state entries in seconds (default: 24 hours)
        """
        self.platform = platform
        self.prefix = f"{platform}_state"
        self.default_ttl = ttl

        # Initialize Redis connection
        if redis_url:
            self.redis = redis.from_url(redis_url)
        else:
            from common.config import REDIS_URL
            self.redis = redis.from_url(REDIS_URL)

        logger.info(f"Initialized {platform} state manager with prefix '{self.prefix}'")

    def _get_key(self, user_id: str) -> str:
        """
        Generate a Redis key for a user state.

        Args:
            user_id: User identifier

        Returns:
            Formatted Redis key
        """
        return f"{self.prefix}:{user_id}"

    async def get_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the state for a user.

        Args:
            user_id: User identifier

        Returns:
            User state dictionary or None if not found
        """
        key = self._get_key(user_id)
        data = self.redis.get(key)

        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in Redis for user {user_id}")
                return None

        return None

    async def set_state(self, user_id: str, state: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Set the state for a user.

        Args:
            user_id: User identifier
            state: State dictionary to store
            ttl: Optional time-to-live in seconds (uses default_ttl if not provided)

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(user_id)
        ttl = ttl or self.default_ttl

        try:
            serialized = json.dumps(state)
            self.redis.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Error setting state for user {user_id}: {e}")
            return False

    async def update_state(self, user_id: str, updates: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Update the state for a user (partial update).

        Args:
            user_id: User identifier
            updates: Dictionary of state updates
            ttl: Optional time-to-live in seconds (uses default_ttl if not provided)

        Returns:
            True if successful, False otherwise
        """
        current_state = await self.get_state(user_id) or {}
        current_state.update(updates)
        return await self.set_state(user_id, current_state, ttl)

    async def clear_state(self, user_id: str) -> bool:
        """
        Clear the state for a user.

        Args:
            user_id: User identifier

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(user_id)
        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error clearing state for user {user_id}: {e}")
            return False

    async def set_conversation_step(self, user_id: str, step: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Set the current step in a conversation flow.

        Args:
            user_id: User identifier
            step: Current conversation step name
            data: Optional data related to the step

        Returns:
            True if successful, False otherwise
        """
        updates = {"state": step}
        if data:
            updates.update(data)

        return await self.update_state(user_id, updates)

    async def get_conversation_step(self, user_id: str) -> Optional[str]:
        """
        Get the current step in a conversation flow.

        Args:
            user_id: User identifier

        Returns:
            Current conversation step or None if not found
        """
        state = await self.get_state(user_id)
        return state.get("state") if state else None

    @classmethod
    def create(cls, platform: str, redis_url: Optional[str] = None, ttl: int = 86400) -> 'PlatformStateManager':
        """
        Factory method to create platform-specific state managers.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            redis_url: Optional Redis URL
            ttl: Default TTL for state entries

        Returns:
            Configured PlatformStateManager instance
        """
        if platform not in ["telegram", "viber", "whatsapp"]:
            logger.warning(f"Unknown platform: {platform}, using generic state manager")

        return cls(platform=platform, redis_url=redis_url, ttl=ttl)

    async def get_or_create_state(self, user_id: str, default_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get existing state or create new state with defaults if not found.

        Args:
            user_id: User identifier
            default_state: Default state to use if none exists

        Returns:
            User state dictionary, either existing or newly created
        """
        state = await self.get_state(user_id)

        if not state:
            state = default_state or {"state": "start"}
            await self.set_state(user_id, state)

        return state


# Create preconfigured instances for each platform
telegram_state_manager = PlatformStateManager.create("telegram")
viber_state_manager = PlatformStateManager.create("viber")
whatsapp_state_manager = PlatformStateManager.create("whatsapp")