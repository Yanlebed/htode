# common/utils/cache_managers.py
import json
import logging
from typing import Dict, Any, List, Optional

from common.utils.cache import redis_client, CacheTTL
from common.utils.cache_invalidation import (
    get_entity_cache_key,
    invalidate_user_caches,
    invalidate_subscription_caches,
    invalidate_ad_caches,
    invalidate_favorite_caches
)

logger = logging.getLogger(__name__)


class BaseCacheManager:
    """Base class for all cache managers"""

    @staticmethod
    def get(key: str) -> Optional[Any]:
        """Get a value from cache"""
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
        """Set a value in cache"""
        redis_client.set(key, json.dumps(value), ex=ttl)

    @staticmethod
    def delete(key: str) -> None:
        """Delete a cache key"""
        redis_client.delete(key)

    @staticmethod
    def key_exists(key: str) -> bool:
        """Check if a key exists in cache"""
        return bool(redis_client.exists(key))


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
        return invalidate_user_caches(user_id)


class SubscriptionCacheManager(BaseCacheManager):
    """Manager for subscription-related cache operations"""

    @staticmethod
    def get_user_subscriptions(user_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached user subscriptions list"""
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
        """Invalidate all ad-related caches"""
        return invalidate_ad_caches(ad_id, resource_url)


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
        return invalidate_favorite_caches(user_id)


# Example usage of the cache managers:
"""
# Get user filters
user_filters = UserCacheManager.get_filters(user_id)
if not user_filters:
    # Cache miss, fetch from database
    user_filters = fetch_user_filters_from_db(user_id)
    UserCacheManager.set_filters(user_id, user_filters)

# Update ad and invalidate cache
with db_session() as db:
    AdRepository.update_ad(db, ad_id, updated_data)
    AdCacheManager.invalidate_all(ad_id, resource_url)
"""