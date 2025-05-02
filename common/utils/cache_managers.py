# common/utils/cache_managers.py
import json
import logging
from typing import Dict, Any, List, Optional, Union

from common.utils.cache import redis_client, CacheTTL, get_entity_cache_key

logger = logging.getLogger(__name__)


class BaseCacheManager:
    """Base class for all cache managers"""

    @staticmethod
    def get(key: str) -> Optional[Any]:
        """Get a value from a cache"""
        data = redis_client.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in cache for key: {key}")
                return None
        return None

    @staticmethod
    def set(key: str, value: Any, ttl: int = CacheTTL.STANDARD) -> None:
        """Set a value in the cache"""
        redis_client.set(key, json.dumps(value), ex=ttl)

    @staticmethod
    def delete(key: str) -> None:
        """Delete a cache key"""
        redis_client.delete(key)

    @staticmethod
    def key_exists(key: str) -> bool:
        """Check if a key exists in the cache"""
        return bool(redis_client.exists(key))

    @staticmethod
    def delete_pattern(pattern: str) -> int:
        """
        Delete all keys matching a pattern

        Args:
            pattern: Redis a key pattern to match (e.g., "user:*:filters")

        Returns:
            Number of deleted keys
        """
        keys = redis_client.keys(pattern)
        if keys:
            return redis_client.delete(*keys)
        return 0

    @staticmethod
    def delete_keys(keys: List[str]) -> int:
        """
        Delete multiple keys

        Args:
            keys: List of keys to delete

        Returns:
            Number of deleted keys
        """
        if not keys:
            return 0

        existing_keys = [key for key in keys if redis_client.exists(key)]
        if existing_keys:
            return redis_client.delete(*existing_keys)
        return 0

    @staticmethod
    def invalidate_keys_for_entity(entity_type: str, entity_id: Union[int, str],
                                   extra_patterns: List[str] = None) -> int:
        """
        Invalidate all keys related to a specific entity

        Args:
            entity_type: Type of entity (e.g., 'user', 'ad')
            entity_id: Entity ID
            extra_patterns: Optional additional patterns to match

        Returns:
            Number of invalidated keys
        """
        # Base pattern for this entity
        pattern = f"{entity_type}:{entity_id}*"
        count = BaseCacheManager.delete_pattern(pattern)

        # Process additional patterns if provided
        if extra_patterns:
            for extra_pattern in extra_patterns:
                count += BaseCacheManager.delete_pattern(extra_pattern)

        return count


class UserCacheManager(BaseCacheManager):
    """Manager for user-related cache operations"""

    @staticmethod
    def get_filters(user_id: int) -> Optional[Dict[str, Any]]:
        """Get cached user filters"""
        key = get_entity_cache_key("user_filters", user_id)
        return BaseCacheManager.get(key)

    @staticmethod
    def set_filters(user_id: int, filters_data: Dict[str, Any], ttl: int = CacheTTL.MEDIUM) -> None:
        """Cache user filters"""
        key = get_entity_cache_key("user_filters", user_id)
        BaseCacheManager.set(key, filters_data, ttl)

    @staticmethod
    def get_subscription_status(user_id: int) -> Optional[Dict[str, Any]]:
        """Get cached subscription status"""
        key = get_entity_cache_key("subscription_status", user_id)
        return BaseCacheManager.get(key)

    @staticmethod
    def set_subscription_status(user_id: int, status_data: Dict[str, Any], ttl: int = CacheTTL.MEDIUM) -> None:
        """Cache subscription status"""
        key = get_entity_cache_key("subscription_status", user_id)
        BaseCacheManager.set(key, status_data, ttl)

    @staticmethod
    def invalidate_all(user_id: int) -> int:
        """Invalidate all user-related caches"""
        from common.utils.cache_invalidation import invalidate_user_caches
        return invalidate_user_caches(user_id)


class SubscriptionCacheManager(BaseCacheManager):
    """Manager for subscription-related cache operations"""

    @staticmethod
    def get_user_subscriptions(user_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get a cached user subscriptions list"""
        key = get_entity_cache_key("user_subscriptions_list", user_id)
        return BaseCacheManager.get(key)

    @staticmethod
    def set_user_subscriptions(user_id: int, subscriptions: List[Dict[str, Any]], ttl: int = CacheTTL.MEDIUM) -> None:
        """Cache user subscriptions list"""
        key = get_entity_cache_key("user_subscriptions_list", user_id)
        BaseCacheManager.set(key, subscriptions, ttl)

    @staticmethod
    def invalidate_all(user_id: int, subscription_id: Optional[int] = None) -> int:
        """Invalidate all subscription-related caches"""
        from common.utils.cache_invalidation import invalidate_subscription_caches
        return invalidate_subscription_caches(user_id, subscription_id)


class AdCacheManager(BaseCacheManager):
    """Manager for ad-related cache operations"""

    @staticmethod
    def get_full_ad_data(ad_id: int) -> Optional[Dict[str, Any]]:
        """Get cached full ad data"""
        key = get_entity_cache_key("full_ad", ad_id)
        return BaseCacheManager.get(key)

    @staticmethod
    def set_full_ad_data(ad_id: int, ad_data: Dict[str, Any], ttl: int = CacheTTL.MEDIUM) -> None:
        """Cache full ad data"""
        key = get_entity_cache_key("full_ad", ad_id)
        BaseCacheManager.set(key, ad_data, ttl)

    @staticmethod
    def get_ad_images(ad_id: int) -> Optional[List[str]]:
        """Get cached ad images"""
        key = get_entity_cache_key("ad_images", ad_id)
        return BaseCacheManager.get(key)

    @staticmethod
    def set_ad_images(ad_id: int, images: List[str], ttl: int = CacheTTL.LONG) -> None:
        """Cache ad images"""
        key = get_entity_cache_key("ad_images", ad_id)
        BaseCacheManager.set(key, images, ttl)

    @staticmethod
    def get_ad_description(resource_url: str) -> Optional[str]:
        """Get cached ad description"""
        key = get_entity_cache_key("ad_description", resource_url)
        data = redis_client.get(key)
        return data.decode('utf-8') if data else None

    @staticmethod
    def set_ad_description(resource_url: str, description: str, ttl: int = CacheTTL.LONG) -> None:
        """Cache ad description"""
        key = get_entity_cache_key("ad_description", resource_url)
        redis_client.set(key, description, ex=ttl)

    @staticmethod
    def invalidate_all(ad_id: int, resource_url: Optional[str] = None) -> int:
        """
        Invalidate all ad-related caches

        Args:
            ad_id: Ad ID
            resource_url: Optional resource URL

        Returns:
            Number of invalidated keys
        """
        # Collect keys to delete
        keys_to_delete = [
            get_entity_cache_key("full_ad", ad_id),
            get_entity_cache_key("ad_images", ad_id),
            get_entity_cache_key("matching_users", ad_id)
        ]

        # Add resource URL-related keys
        if resource_url:
            keys_to_delete.extend([
                get_entity_cache_key("extra_images", resource_url),
                get_entity_cache_key("ad_description", resource_url)
            ])

        # Delete all collected keys
        deleted_count = BaseCacheManager.delete_keys(keys_to_delete)

        # Also delete any pattern-based keys that might be related
        pattern_keys = [
            f"ad:{ad_id}:*",
            f"matching_users:*"  # This might be broader than needed
        ]

        for pattern in pattern_keys:
            deleted_count += BaseCacheManager.delete_pattern(pattern)

        logger.debug(f"Invalidated {deleted_count} cache keys for ad {ad_id}")
        return deleted_count


class FavoriteCacheManager(BaseCacheManager):
    """Manager for favorite-related cache operations"""

    @staticmethod
    def get_user_favorites(user_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached user favorites"""
        key = get_entity_cache_key("user_favorites", user_id)
        return BaseCacheManager.get(key)

    @staticmethod
    def set_user_favorites(user_id: int, favorites: List[Dict[str, Any]], ttl: int = CacheTTL.MEDIUM) -> None:
        """Cache user favorites"""
        key = get_entity_cache_key("user_favorites", user_id)
        BaseCacheManager.set(key, favorites, ttl)

    @staticmethod
    def invalidate_all(user_id: int) -> int:
        """Invalidate all favorite-related caches"""
        from common.utils.cache_invalidation import invalidate_favorite_caches
        return invalidate_favorite_caches(user_id)