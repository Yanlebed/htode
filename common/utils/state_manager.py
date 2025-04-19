# common/utils/state_manager.py

import json
import redis
import logging
from typing import Optional, Dict, Any
from common.config import REDIS_URL

logger = logging.getLogger(__name__)


class RedisStateManager:
    """
    A Redis-based state manager for storing user conversation states.
    """

    def __init__(self, redis_url: str = REDIS_URL, prefix: str = 'state'):
        """
        Initialize the state manager.

        Args:
            redis_url: Redis connection URL
            prefix: Prefix for Redis keys
        """
        self.redis = redis.from_url(redis_url)
        self.prefix = prefix
        logger.info(f"Initialized RedisStateManager with prefix '{prefix}'")

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

    async def set_state(self, user_id: str, state: Dict[str, Any], ttl: int = 86400) -> bool:
        """
        Set the state for a user.

        Args:
            user_id: User identifier
            state: State dictionary to store
            ttl: Time-to-live in seconds (default: 24 hours)

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(user_id)
        try:
            serialized = json.dumps(state)
            self.redis.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Error setting state for user {user_id}: {e}")
            return False

    async def update_state(self, user_id: str, updates: Dict[str, Any], ttl: int = 86400) -> bool:
        """
        Update the state for a user (partial update).

        Args:
            user_id: User identifier
            updates: Dictionary of state updates
            ttl: Time-to-live in seconds (default: 24 hours)

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