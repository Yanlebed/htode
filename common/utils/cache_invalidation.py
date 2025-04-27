# common/utils/cache_invalidation.py

import logging
from typing import Optional, List, Union

from common.utils.cache import redis_client
from common.utils.cache_managers import (
    BaseCacheManager,
    UserCacheManager,
    AdCacheManager,
    SubscriptionCacheManager,
    FavoriteCacheManager
)

logger = logging.getLogger(__name__)


def get_entity_cache_key(entity_type: str, entity_id: Union[int, str], suffix: Optional[str] = None) -> str:
    """
    Generate a standardized cache key for an entity.

    Args:
        entity_type: Type of entity (e.g., 'user', 'ad', 'subscription')
        entity_id: Entity identifier
        suffix: Optional additional suffix

    Returns:
        A standardized cache key string
    """
    key = f"{entity_type}:{entity_id}"
    if suffix:
        key += f":{suffix}"
    return key


def invalidate_user_caches(user_id: int) -> int:
    """
    Invalidate all caches related to a user.

    Args:
        user_id: Database user ID

    Returns:
        Number of invalidated cache keys
    """
    return UserCacheManager.invalidate_all(user_id)


def invalidate_subscription_caches(user_id: int, subscription_id: Optional[int] = None) -> int:
    """
    Invalidate all subscription-related caches for a user.

    Args:
        user_id: Database user ID
        subscription_id: Optional specific subscription ID

    Returns:
        Number of invalidated cache keys
    """
    return SubscriptionCacheManager.invalidate_all(user_id, subscription_id)


def invalidate_ad_caches(ad_id: int, resource_url: Optional[str] = None) -> int:
    """
    Invalidate all caches related to an ad.

    Args:
        ad_id: Database ad ID
        resource_url: Optional resource URL of the ad

    Returns:
        Number of invalidated cache keys
    """
    return AdCacheManager.invalidate_all(ad_id, resource_url)


def invalidate_favorite_caches(user_id: int) -> int:
    """
    Invalidate favorite-related caches for a user.

    Args:
        user_id: Database user ID

    Returns:
        Number of invalidated cache keys
    """
    return FavoriteCacheManager.invalidate_all(user_id)


def invalidate_phone_caches(ad_id: int) -> int:
    """
    Invalidate phone-related caches for an ad.

    Args:
        ad_id: Database ad ID

    Returns:
        Number of invalidated cache keys
    """
    # Invalidate full ad cache since it contains phone information
    return invalidate_ad_caches(ad_id)


def warm_cache_for_user(user_id: int) -> None:
    """
    Warm up commonly accessed caches for a user to improve performance.
    This should be called when a user logs in or starts a new session.

    Args:
        user_id: Database user ID
    """
    from common.db.operations import (
        get_user_filters,
        list_favorites,
        get_subscription_data_for_user,
        batch_get_full_ad_data
    )

    logger.info(f"Warming cache for user_id: {user_id}")

    try:
        # Prefetch user filters
        filters = get_user_filters(user_id)

        # Store in cache using manager
        if filters:
            UserCacheManager.set_filters(user_id, filters)

        # Prefetch user's favorites
        favorites = list_favorites(user_id)

        # Store in cache using manager
        if favorites:
            FavoriteCacheManager.set_user_favorites(user_id, favorites)

        # Prefetch subscription data
        subscription_data = get_subscription_data_for_user(user_id)

        # Store in cache using manager
        if subscription_data:
            SubscriptionCacheManager.set_user_subscriptions(user_id, [subscription_data])

        # If we have favorites, prefetch full data for those ads
        if favorites:
            ad_ids = [fav.get('ad_id') for fav in favorites if fav.get('ad_id')]
            ad_data_dict = batch_get_full_ad_data(ad_ids)

            # Store each ad in cache using manager
            for ad_id, ad_data in ad_data_dict.items():
                if ad_data:
                    AdCacheManager.set_full_ad_data(ad_id, ad_data)

        logger.info(f"Cache warmed for user_id: {user_id}")
    except Exception as e:
        logger.error(f"Error warming cache for user {user_id}: {e}")