# common/utils/cache_invalidation.py

import logging
from typing import Optional, List, Union

from common.utils.cache import redis_client

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
    # List of standard user-related cache prefixes
    prefixes = [
        "user_filters",
        "user_subscriptions_list",
        "user_favorites",
        "user_subscription",
        "subscription_status",
        "user_subscription:True",  # For free subscription
        "user_subscription:False"  # For paid subscription
    ]

    # Individual keys to invalidate
    keys_to_delete = [get_entity_cache_key(prefix, user_id) for prefix in prefixes]

    # Additional pattern-based keys
    pattern_keys = [
        f"matching_users:*",  # Invalidate any ad matches for this user
        f"user_subscriptions_paginated:{user_id}:*",  # Invalidate paginated subscription caches
    ]

    # Collect all pattern-matching keys
    for pattern in pattern_keys:
        matching_keys = redis_client.keys(pattern)
        if matching_keys:
            keys_to_delete.extend(matching_keys)

    # Delete all collected keys
    count = 0
    if keys_to_delete:
        existing_keys = [key for key in keys_to_delete if redis_client.exists(key)]
        if existing_keys:
            count = redis_client.delete(*existing_keys)
            logger.debug(f"Invalidated {count} cache keys for user {user_id}")

    return count


def invalidate_subscription_caches(user_id: int, subscription_id: Optional[int] = None) -> int:
    """
    Invalidate all subscription-related caches for a user.

    Args:
        user_id: Database user ID
        subscription_id: Optional specific subscription ID

    Returns:
        Number of invalidated cache keys
    """
    keys_to_delete = [
        get_entity_cache_key("user_filters", user_id),
        get_entity_cache_key("user_subscriptions_list", user_id),
        get_entity_cache_key("subscription_status", user_id)
    ]

    if subscription_id:
        keys_to_delete.append(get_entity_cache_key("subscription", subscription_id))

    # Pattern-based keys
    pattern_keys = [
        "matching_users:*",  # Invalidate any matching users patterns for ads
        f"user_subscriptions_paginated:{user_id}:*",  # Invalidate all paginated subscription caches
    ]

    # Collect all pattern-matching keys
    for pattern in pattern_keys:
        matching_keys = redis_client.keys(pattern)
        if matching_keys:
            keys_to_delete.extend(matching_keys)

    # Delete all collected keys
    count = 0
    if keys_to_delete:
        existing_keys = [key for key in keys_to_delete if redis_client.exists(key)]
        if existing_keys:
            count = redis_client.delete(*existing_keys)
            logger.debug(f"Invalidated {count} subscription cache keys for user {user_id}")

    return count


def invalidate_ad_caches(ad_id: int, resource_url: Optional[str] = None) -> int:
    """
    Invalidate all caches related to an ad.

    Args:
        ad_id: Database ad ID
        resource_url: Optional resource URL of the ad

    Returns:
        Number of invalidated cache keys
    """
    keys_to_delete = [
        get_entity_cache_key("full_ad", ad_id),
        get_entity_cache_key("ad_images", ad_id),
        get_entity_cache_key("matching_users", ad_id)
    ]

    if resource_url:
        keys_to_delete.extend([
            get_entity_cache_key("extra_images", resource_url),
            get_entity_cache_key("ad_description", resource_url)
        ])

    # Delete all collected keys
    count = 0
    if keys_to_delete:
        existing_keys = [key for key in keys_to_delete if redis_client.exists(key)]
        if existing_keys:
            count = redis_client.delete(*existing_keys)
            logger.debug(f"Invalidated {count} cache keys for ad {ad_id}")

    return count


def invalidate_favorite_caches(user_id: int) -> int:
    """
    Invalidate favorite-related caches for a user.

    Args:
        user_id: Database user ID

    Returns:
        Number of invalidated cache keys
    """
    keys_to_delete = [
        get_entity_cache_key("user_favorites", user_id)
    ]

    # Delete all collected keys
    count = 0
    if keys_to_delete:
        existing_keys = [key for key in keys_to_delete if redis_client.exists(key)]
        if existing_keys:
            count = redis_client.delete(*existing_keys)
            logger.debug(f"Invalidated {count} favorite cache keys for user {user_id}")

    return count


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
        get_user_filters(user_id)

        # Prefetch user's favorites
        favorites = list_favorites(user_id)

        # Prefetch subscription data
        get_subscription_data_for_user(user_id)

        # If we have favorites, prefetch full data for those ads
        if favorites:
            ad_ids = [fav.get('ad_id') for fav in favorites if fav.get('ad_id')]
            batch_get_full_ad_data(ad_ids)

        logger.info(f"Cache warmed for user_id: {user_id}")
    except Exception as e:
        logger.error(f"Error warming cache for user {user_id}: {e}")