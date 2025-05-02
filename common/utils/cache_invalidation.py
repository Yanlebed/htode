# common/utils/cache_invalidation.py

import logging
from typing import Optional, List, Union

# Import only BaseCacheManager to avoid circular imports
from common.utils.cache_managers import BaseCacheManager
from common.utils.cache import get_entity_cache_key

logger = logging.getLogger(__name__)


def invalidate_ad_caches(ad_id: int, resource_url: Optional[str] = None) -> int:
    """
    Invalidate all caches related to an ad.

    Args:
        ad_id: Database ad ID
        resource_url: Optional resource URL of the ad

    Returns:
        Number of invalidated cache keys
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
    from common.utils.cache_managers import UserCacheManager, FavoriteCacheManager, SubscriptionCacheManager, AdCacheManager

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


def invalidate_user_caches(user_id: int) -> int:
    """
    Invalidate all caches related to a user.

    Args:
        user_id: Database user ID

    Returns:
        Number of invalidated cache keys
    """
    patterns = [
        f"user:{user_id}*",
        f"user_filters:{user_id}*",
        f"subscription_status:{user_id}*",
        f"user_favorites:{user_id}*",
        f"user_subscriptions_list:{user_id}*"
    ]

    deleted_count = 0
    for pattern in patterns:
        deleted_count += BaseCacheManager.delete_pattern(pattern)

    logger.debug(f"Invalidated {deleted_count} cache keys for user {user_id}")
    return deleted_count


def invalidate_subscription_caches(user_id: int, subscription_id: Optional[int] = None) -> int:
    """
    Invalidate all subscription-related caches for a user.

    Args:
        user_id: Database user ID
        subscription_id: Optional specific subscription ID

    Returns:
        Number of invalidated cache keys
    """
    patterns = [
        f"user_subscriptions_list:{user_id}*",
        f"user_filters:{user_id}*",
        f"subscription_status:{user_id}*"
    ]

    if subscription_id:
        patterns.append(f"subscription:{subscription_id}*")

    deleted_count = 0
    for pattern in patterns:
        deleted_count += BaseCacheManager.delete_pattern(pattern)

    logger.debug(f"Invalidated {deleted_count} subscription cache keys for user {user_id}")
    return deleted_count


def invalidate_favorite_caches(user_id: int) -> int:
    """
    Invalidate favorite-related caches for a user.

    Args:
        user_id: Database user ID

    Returns:
        Number of invalidated cache keys
    """
    patterns = [
        f"user_favorites:{user_id}*"
    ]

    deleted_count = 0
    for pattern in patterns:
        deleted_count += BaseCacheManager.delete_pattern(pattern)

    logger.debug(f"Invalidated {deleted_count} favorite cache keys for user {user_id}")
    return deleted_count