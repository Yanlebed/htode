# common/utils/cache_invalidation.py

import logging
from typing import Optional, List, Union

from common.utils.cache_managers import (
    UserCacheManager,
    AdCacheManager,
    SubscriptionCacheManager,
    FavoriteCacheManager
)

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
    return AdCacheManager.invalidate_all(ad_id, resource_url)


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