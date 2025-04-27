# common/db/operations.py

"""
This module contains database operations that combine models and repositories.
It should be imported after both models and repositories are initialized.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta

from sqlalchemy import or_

from common.db.session import db_session
from common.db.models.user import User
from common.db.models.subscription import UserFilter
from common.db.models.ad import Ad, AdPhone
from common.db.repositories.user_repository import UserRepository
from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.repositories.ad_repository import AdRepository
from common.db.repositories.favorite_repository import FavoriteRepository
from common.utils.cache import redis_cache, CacheTTL, batch_get_cached, batch_set_cached, redis_client
from common.config import GEO_ID_MAPPING, get_key_by_value
from common.utils.phone_parser import extract_phone_numbers_from_resource
from common.utils.cache_invalidation import (
    invalidate_user_caches,
    invalidate_subscription_caches,
    invalidate_ad_caches,
    invalidate_favorite_caches,
    warm_cache_for_user
)

from common.utils.cache_managers import (
    UserCacheManager,
    SubscriptionCacheManager,
    AdCacheManager,
    FavoriteCacheManager
)

logger = logging.getLogger(__name__)

# Batch size for operations to balance between network round trips and memory usage
BATCH_SIZE = 100


def get_or_create_user(messenger_id, messenger_type="telegram"):
    """
    Get or create a user with telegram_id, viber_id, or whatsapp_id
    """
    logger.info(f"Getting user with {messenger_type} id: {messenger_id}")

    with db_session() as db:
        # Get user by messenger ID
        user = UserRepository.get_by_messenger_id(db, messenger_id, messenger_type)

        if user:
            logger.info(f"Found user with {messenger_type} id: {messenger_id}")
            return user.id

        logger.info(f"Creating user with {messenger_type} id: {messenger_id}")

        # Create a new user
        free_until = datetime.now() + timedelta(days=7)

        # Create user with the appropriate messenger ID
        user = UserRepository.create_messenger_user(db, messenger_id, messenger_type, free_until)
        return user.id


def update_user_filter(user_id, filters):
    """
    Update filters for a user with cache invalidation
    """
    logger.info(f"Updating filters for user_id: {user_id}")

    try:
        with db_session() as db:
            # Check if user exists
            user = UserRepository.get_by_id(db, user_id)
            if not user:
                logger.error(f"Cannot update filters - user_id {user_id} does not exist in database")
                raise ValueError(f"User ID {user_id} does not exist")

            # Extract filter data
            property_type = filters.get('property_type')
            city = filters.get('city')
            geo_id = get_key_by_value(city, GEO_ID_MAPPING)
            rooms_count = filters.get('rooms')  # List or None
            price_min = filters.get('price_min')
            price_max = filters.get('price_max')

            # Create filter data dictionary
            filter_data = {
                'property_type': property_type,
                'city': geo_id,
                'rooms_count': rooms_count,
                'price_min': price_min,
                'price_max': price_max
            }

            # Update or create user filter
            user_filter = SubscriptionRepository.update_user_filter(db, user_id, filter_data)

            logger.info(
                f"Updated filters: [{user_id}, {property_type}, {geo_id}, {rooms_count}, {price_min}, {price_max}]")

            # Use centralized cache invalidation
            invalidate_subscription_caches(user_id)

            return user_filter

    except Exception as e:
        logger.error(f"Error updating user filters: {e}")
        raise


def invalidate_user_filter_caches(user_id: int):
    """Centralized function to invalidate all related caches when a user filter changes"""
    # Invalidate user filter cache
    redis_client.delete(f"user_filters:{user_id}")

    # Invalidate subscription list cache
    redis_client.delete(f"user_subscriptions_list:{user_id}")

    # Invalidate matching users cache for ads
    matching_pattern = "matching_users:*"
    matching_keys = redis_client.keys(matching_pattern)
    if matching_keys:
        redis_client.delete(*matching_keys)

    # Invalidate subscription status cache
    redis_client.delete(f"subscription_status:{user_id}")


def get_user_filters(user_id):
    """Get user filters with caching"""
    # Try to get from cache first using the cache manager
    filters = UserCacheManager.get_filters(user_id)
    if filters:
        return filters

    # Cache miss, query the database
    with db_session() as db:
        filters = SubscriptionRepository.get_user_filters(db, user_id)

        # Cache the result if found
        if filters:
            UserCacheManager.set_filters(user_id, filters)

        return filters


def batch_get_user_filters(user_ids):
    """
    Get filters for multiple users in a single query to prevent N+1 problems
    """
    if not user_ids:
        return {}

    # Try to get from cache first
    cached_results = batch_get_cached(user_ids, prefix="user_filters")

    # Identify which user_ids were not in cache
    missing_user_ids = [uid for uid in user_ids if uid not in cached_results]

    if not missing_user_ids:
        return cached_results

    # Fetch missing data from database in batches to avoid huge IN clauses
    results = dict(cached_results)  # Start with cached results

    with db_session() as db:
        for i in range(0, len(missing_user_ids), BATCH_SIZE):
            batch = missing_user_ids[i:i + BATCH_SIZE]

            # Use repository to get filters for this batch
            batch_results = {}
            for user_id in batch:
                user_filter = SubscriptionRepository.get_user_filters(db, user_id)
                if user_filter:
                    results[user_id] = user_filter
                    batch_results[user_id] = user_filter

            # Cache the batch results
            batch_set_cached(batch_results, ttl=CacheTTL.MEDIUM, prefix="user_filters")

    return results


def get_db_user_id_by_telegram_id(messenger_id, messenger_type="telegram"):
    """
    Get database user ID from messenger-specific ID (telegram_id, viber_id, or whatsapp_id).
    """
    logger.info(f"Getting database user ID for {messenger_type} ID: {messenger_id}")

    try:
        with db_session() as db:
            user = UserRepository.get_by_messenger_id(db, messenger_id, messenger_type)

            if user:
                logger.info(f"Found database user ID {user.id} for {messenger_type} ID: {messenger_id}")
                return user.id

        logger.warning(f"No database user found for {messenger_type} ID: {messenger_id}")
        return None
    except Exception as e:
        logger.error(f"Error finding user by messenger ID: {e}")
        return None


def get_platform_ids_for_user(user_id: int) -> dict:
    """
    Get all messaging platform IDs for a user.

    Args:
        user_id: Database user ID

    Returns:
        Dictionary with platform IDs (telegram_id, viber_id, whatsapp_id)
    """
    try:
        with db_session() as db:
            user = UserRepository.get_by_id(db, user_id)

            if not user:
                return {}

            # Create a cleaned dictionary with only non-None values
            platform_ids = {}
            if user.telegram_id is not None:
                platform_ids["telegram_id"] = user.telegram_id

            if user.viber_id is not None:
                platform_ids["viber_id"] = user.viber_id

            if user.whatsapp_id is not None:
                platform_ids["whatsapp_id"] = user.whatsapp_id

            return platform_ids
    except Exception as e:
        logger.error(f"Error getting platform IDs for user {user_id}: {e}")
        return {}


def find_users_for_ad(ad):
    """
    Finds users whose subscription filters match this ad.
    Now with Redis caching and batch processing to improve performance.
    """
    try:
        # Extract the ad ID for caching
        ad_id = ad.get('id') if isinstance(ad, dict) else ad.id if hasattr(ad, 'id') else None

        if not ad_id:
            logger.error("Cannot find users for ad without ID")
            return []

        # Create a cache key based on the ad's primary attributes that affect matching
        cache_key = f"matching_users:{ad_id}"

        # Try to get results from cache first
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f'Cache hit for ad {ad_id} matching users')
            return json.loads(cached)

        logger.info(f'Looking for users for ad: {ad}')

        with db_session() as db:
            # Use repository to find matching users
            if isinstance(ad, dict):
                existing_ad = db.query(Ad).get(ad_id)
                if not existing_ad:
                    # Create temporary Ad object for matching
                    ad_obj = Ad(
                        id=ad_id,
                        property_type=ad.get('property_type'),
                        city=ad.get('city'),
                        rooms_count=ad.get('rooms_count'),
                        price=ad.get('price')
                    )
                else:
                    ad_obj = existing_ad
            else:
                ad_obj = ad

            # Use repository to find matching users
            user_ids = AdRepository.find_users_for_ad(db, ad_obj)

        # Cache the results for 1 hour
        redis_client.set(cache_key, json.dumps(user_ids), ex=3600)

        logger.info(f'Found {len(user_ids)} users for ad: {ad_id}')
        return user_ids

    except Exception as e:
        logger.error(
            f"Error finding users for ad {ad.get('id') if isinstance(ad, dict) else getattr(ad, 'id', 'unknown')}: {e}")
        return []


def batch_find_users_for_ads(ads):
    """
    Find matching users for multiple ads in an efficient way
    using IN clauses and eager loading where possible.

    Args:
        ads: List of ad dictionaries

    Returns:
        Dict mapping ad_id to list of matching user_ids
    """
    if not ads:
        return {}

    results = {}
    ad_ids = [ad.get('id') for ad in ads if ad.get('id')]

    # Try to get from cache first
    cache_keys = [f"matching_users:{ad_id}" for ad_id in ad_ids]
    cached_results = {}

    for i, key in enumerate(cache_keys):
        cached = redis_client.get(key)
        if cached:
            ad_id = ad_ids[i]
            cached_results[ad_id] = json.loads(cached)

    # Identify which ads were not in cache
    cached_ad_ids = set(cached_results.keys())
    ads_to_process = [ad for ad in ads if ad.get('id') not in cached_ad_ids]

    if not ads_to_process:
        return cached_results

    # Process the remaining ads
    with db_session() as db:
        # Get all active users
        active_users = db.query(User.id).filter(
            or_(
                User.free_until > datetime.now(),
                User.subscription_until > datetime.now()
            )
        ).all()

        active_user_ids = [row[0] for row in active_users]

        if not active_user_ids:
            # No active users, no matches possible
            return cached_results

        # Get all user filters in one query
        user_filters = batch_get_user_filters(active_user_ids)

        # Process each ad against all user filters in memory
        for ad in ads_to_process:
            ad_id = ad.get('id')
            if not ad_id:
                continue

            # Use repository to find matching users for this ad
            with db_session() as db:
                # Convert dict to Ad object if needed
                if isinstance(ad, dict):
                    existing_ad = db.query(Ad).get(ad_id)
                    if not existing_ad:
                        # Create temporary Ad object for matching
                        ad_obj = Ad(
                            id=ad_id,
                            property_type=ad.get('property_type'),
                            city=ad.get('city'),
                            rooms_count=ad.get('rooms_count'),
                            price=ad.get('price')
                        )
                    else:
                        ad_obj = existing_ad
                else:
                    ad_obj = ad

                matching_users = AdRepository.find_users_for_ad(db, ad_obj)

            # Store results and cache them
            results[ad_id] = matching_users
            redis_client.set(f"matching_users:{ad_id}", json.dumps(matching_users), ex=CacheTTL.STANDARD)

    # Combine cached and newly processed results
    results.update(cached_results)
    return results


# Update these functions in common/db/operations.py with cache managers

from common.utils.cache_managers import (
    UserCacheManager,
    SubscriptionCacheManager,
    AdCacheManager,
    FavoriteCacheManager
)


def get_user_filters(user_id):
    """Get user filters with caching"""
    # Try to get from cache first using the cache manager
    filters = UserCacheManager.get_filters(user_id)
    if filters:
        return filters

    # Cache miss, query the database
    with db_session() as db:
        filters = SubscriptionRepository.get_user_filters(db, user_id)

        # Cache the result if found
        if filters:
            UserCacheManager.set_filters(user_id, filters)

        return filters


def get_subscription_data_for_user(user_id: int) -> dict:
    """
    Get subscription data for a user with caching
    """
    # Try to get from cache using the cache manager
    cached_data = SubscriptionCacheManager.get_user_subscriptions(user_id)
    if cached_data:
        return cached_data

    try:
        with db_session() as db:
            user_filter = SubscriptionRepository.get_user_filters(db, user_id)

            if user_filter:
                # Cache for 5 minutes using the cache manager
                SubscriptionCacheManager.set_user_subscriptions(user_id, user_filter)
                return user_filter
            else:
                return None
    except Exception as e:
        logger.error(f"Error getting subscription data for user {user_id}: {e}")
        return None


def get_full_ad_data(ad_id: int):
    """Get complete ad data with related entities and caching"""
    # Try to get from cache using the cache manager
    cached_data = AdCacheManager.get_full_ad_data(ad_id)
    if cached_data:
        return cached_data

    try:
        with db_session() as db:
            ad_data = AdRepository.get_full_ad_data(db, ad_id)

            if ad_data:
                # Cache the result using the cache manager
                AdCacheManager.set_full_ad_data(ad_id, ad_data)

            return ad_data
    except Exception as e:
        logger.error(f"Error getting full ad data for {ad_id}: {e}")
        return None


def batch_get_full_ad_data(ad_ids):
    """
    Get complete data for multiple ads in a single query with efficient caching
    """
    if not ad_ids:
        return {}

    # Result dictionary
    results = {}

    # Step 1: Try to get as many ads from cache as possible
    for ad_id in ad_ids:
        cached_data = AdCacheManager.get_full_ad_data(ad_id)
        if cached_data:
            results[ad_id] = cached_data

    # Step 2: Find which ads weren't in the cache
    missing_ad_ids = [ad_id for ad_id in ad_ids if ad_id not in results]

    # If everything was in cache, return immediately
    if not missing_ad_ids:
        return results

    # Step 3: Process batches of missing ads
    with db_session() as db:
        for batch_start in range(0, len(missing_ad_ids), BATCH_SIZE):
            batch = missing_ad_ids[batch_start:batch_start + BATCH_SIZE]

            for ad_id in batch:
                ad_data = AdRepository.get_full_ad_data(db, ad_id)
                if ad_data:
                    results[ad_id] = ad_data
                    # Cache individual results
                    AdCacheManager.set_full_ad_data(ad_id, ad_data)

    return results


def list_favorites_with_eager_loading(user_id: int):
    """
    List user's favorite ads with eager loading of related data
    This prevents N+1 query problems by loading all related data in a single query
    """
    try:
        with db_session() as db:
            return FavoriteRepository.list_favorites(db, user_id)
    except Exception as e:
        logger.error(f"Error listing favorites with eager loading: {e}")
        return []


def add_subscription(user_id, property_type, city_id, rooms_count, price_min, price_max):
    # Replace with:
    with db_session() as db:
        # Check subscription count
        count = SubscriptionRepository.count_subscriptions(db, user_id)
        if count >= 20:
            raise ValueError("You already have 20 subscriptions, cannot add more.")

        # Create filter data
        filter_data = {
            'property_type': property_type,
            'city': city_id,
            'rooms_count': rooms_count,
            'price_min': price_min,
            'price_max': price_max
        }

        # Add subscription
        subscription = SubscriptionRepository.add_subscription(db, user_id, filter_data)

        # Invalidate cache
        invalidate_user_filter_caches(user_id)

        return subscription.id


def list_subscriptions(user_id: int):
    """List user subscriptions with caching"""
    cache_key = f"user_subscriptions_list:{user_id}"
    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    try:
        with db_session() as db:
            subscriptions = SubscriptionRepository.list_subscriptions(db, user_id)

            # Cache for 5 minutes
            redis_client.set(cache_key, json.dumps(subscriptions), ex=CacheTTL.MEDIUM)

            return subscriptions
    except Exception as e:
        logger.error(f"Error listing subscriptions for user {user_id}: {e}")
        return []


def remove_subscription(subscription_id: int, user_id: int) -> bool:
    """
    Remove a subscription with cache invalidation
    """
    try:
        with db_session() as db:
            success = SubscriptionRepository.remove_subscription(db, subscription_id, user_id)

            # Invalidate relevant cache entries
            invalidate_user_filter_caches(user_id)

            return success
    except Exception as e:
        logger.error(f"Error removing subscription {subscription_id} for user {user_id}: {e}")
        return False


def update_subscription(subscription_id: int, user_id: int, new_values: dict):
    """
    Update a subscription with cache invalidation
    """
    try:
        with db_session() as db:
            # Get the subscription
            subscription = db.query(UserFilter).filter(
                UserFilter.id == subscription_id,
                UserFilter.user_id == user_id
            ).first()

            if not subscription:
                return False

            # Update values
            for key, value in new_values.items():
                setattr(subscription, key, value)

            db.commit()

            # Invalidate relevant cache entries
            invalidate_user_filter_caches(user_id)

            return True
    except Exception as e:
        logger.error(f"Error updating subscription {subscription_id} for user {user_id}: {e}")
        return False


def add_favorite_ad(user_id: int, ad_id: int) -> Optional[int]:
    """
    Add a favorite ad with cache invalidation

    Returns:
        Favorite ID or None if failed
    """
    try:
        with db_session() as db:
            # Use repository to add favorite
            favorite = FavoriteRepository.add_favorite(db, user_id, ad_id)

            # Use centralized cache invalidation
            invalidate_favorite_caches(user_id)

            return favorite.id if favorite else None
    except ValueError as e:
        # This handles the case where user already has 50 favorites
        logger.warning(f"Couldn't add favorite: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error adding favorite ad: {e}")
        return None


def list_favorites(user_id):
    """List user's favorite ads with caching"""
    # Try to get from cache using the cache manager
    cached_favorites = FavoriteCacheManager.get_user_favorites(user_id)
    if cached_favorites:
        return cached_favorites

    try:
        with db_session() as db:
            favorites = FavoriteRepository.list_favorites(db, user_id)

            # Cache for 5 minutes using the cache manager
            FavoriteCacheManager.set_user_favorites(user_id, favorites)

            return favorites
    except Exception as e:
        logger.error(f"Error listing favorites: {e}")
        return []


def remove_favorite_ad(user_id: int, ad_id: int) -> bool:
    """Remove a favorite ad with cache invalidation"""
    try:
        with db_session() as db:
            # Use repository to remove favorite
            success = FavoriteRepository.remove_favorite(db, user_id, ad_id)

            # Use centralized cache invalidation
            invalidate_favorite_caches(user_id)

            return success
    except Exception as e:
        logger.error(f"Error removing favorite ad: {e}")
        return False


def get_extra_images(resource_url):
    """Get extra images for an ad with caching"""

    cache_key = f"extra_images:{resource_url}"
    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    try:
        with db_session() as db:
            # First, look up the ad using resource_url
            ad = AdRepository.get_by_resource_url(db, resource_url)
            if not ad:
                return []

            # Get images for the ad
            images = AdRepository.get_ad_images(db, ad.id)

            # Cache for 1 hour - images rarely change
            redis_client.set(cache_key, json.dumps(images), ex=3600)

            return images
    except Exception as e:
        logger.error(f"Error getting extra images: {e}")
        return []


def get_full_ad_description(resource_url):
    """Get full ad description with caching"""
    # Try to get from cache using the cache manager
    cached_description = AdCacheManager.get_ad_description(resource_url)
    if cached_description:
        return cached_description

    logger.info(f'Getting full ad description for resource_url: {resource_url}...')

    try:
        with db_session() as db:
            description = AdRepository.get_description_by_resource_url(db, resource_url)

        if description:
            # Cache for 1 hour using the cache manager
            AdCacheManager.set_ad_description(resource_url, description)

        return description
    except Exception as e:
        logger.error(f"Error getting full ad description: {e}")
        return None


def store_ad_phones(resource_url: str, ad_id: int) -> int:
    """
    Extracts phone numbers and stores them with cache invalidation
    """
    try:
        with db_session() as db:
            # First check if the ad exists in the database
            ad = AdRepository.get_by_id(db, ad_id)

            if not ad:
                logger.warning(f"Cannot store phones for ad_id={ad_id} - ad doesn't exist in the database")
                return 0

            # Extract phones from resource
            result = extract_phone_numbers_from_resource(resource_url)
            phones = result.phone_numbers
            viber_link = result.viber_link

            # Delete existing phones for this ad to avoid duplicates
            phones_count = db.query(AdPhone).filter(AdPhone.ad_id == ad_id).delete()
            logger.info(f"Deleted {phones_count} existing phones for ad_id={ad_id}")

            phones_added = 0

            # Insert new phones
            for phone in phones:
                AdRepository.add_phone(db, ad_id, phone)
                phones_added += 1

            # Insert viber link if available
            if viber_link:
                AdRepository.add_phone(db, ad_id, None, viber_link)

            # Commit changes
            db.commit()

            # Use centralized cache invalidation
            invalidate_ad_caches(ad_id, resource_url)

            return phones_added
    except Exception as e:
        logger.error(f"Error extracting or storing phones for ad {ad_id}: {e}")
        return 0


def warm_cache_for_user(user_id):
    """
    Warm up cache for a user's most commonly accessed data
    Call this when user logs in or starts interacting with the system
    """
    from common.utils.cache_invalidation import warm_cache_for_user as warm_cache
    return warm_cache(user_id)


def start_free_subscription_of_user(user_id: int) -> bool:
    """
    Start or extend a user's free subscription period for 7 days.

    Args:
        user_id: Database user ID

    Returns:
        True if successful, False otherwise
    """
    try:
        with db_session() as db:
            result = UserRepository.start_free_subscription(db, user_id)

        # Use centralized cache invalidation
        invalidate_user_caches(user_id)

        logger.info(f"Started free subscription for user {user_id}")
        return result
    except Exception as e:
        logger.error(f"Error starting free subscription for user {user_id}: {e}")
        return False


def get_subscription_until_for_user(user_id: int, free: bool = False) -> Optional[str]:
    """
    Get the subscription expiration date for a user.

    Args:
        user_id: Database user ID
        free: If True, returns free_until date, otherwise returns subscription_until date

    Returns:
        Subscription expiration date as string or None if not found
    """
    cache_key = f"user_subscription:{user_id}:{free}"
    cached = redis_client.get(cache_key)

    if cached:
        return cached.decode('utf-8')

    try:
        with db_session() as db:
            user = UserRepository.get_by_id(db, user_id)

            if not user:
                return None

            # Get the appropriate date field
            if free:
                date_value = user.free_until
            else:
                date_value = user.subscription_until

            if date_value:
                if isinstance(date_value, datetime):
                    formatted_date = date_value.strftime("%d.%m.%Y")
                else:
                    formatted_date = str(date_value)

                # Cache for 10 minutes
                redis_client.set(cache_key, formatted_date, ex=600)
                return formatted_date

        return None
    except Exception as e:
        logger.error(f"Error getting subscription date for user {user_id}: {e}")
        return None


def get_ad_images(ad_id: Union[int, Dict[str, Any]]) -> List[str]:
    """
    Get all images associated with an ad with caching.
    """
    try:
        # Handle either an ad dict or direct ad_id
        if isinstance(ad_id, dict):
            ad_id = ad_id.get('id')

        if not ad_id:
            return []

        # Try to get from cache using the cache manager
        cached_images = AdCacheManager.get_ad_images(ad_id)
        if cached_images:
            return cached_images

        # Cache miss, query database for images
        with db_session() as db:
            image_urls = AdRepository.get_ad_images(db, ad_id)

            # Cache the result using the cache manager
            if image_urls:
                AdCacheManager.set_ad_images(ad_id, image_urls)

            return image_urls

    except Exception as e:
        logger.error(f"Error getting ad images: {e}")
        return []


def disable_subscription_for_user(user_id: int) -> bool:
    """
    Disable subscription for a user by setting is_paused to True in user_filters table

    Args:
        user_id: User's database ID

    Returns:
        True if successful, False otherwise
    """
    try:
        with db_session() as db:
            success = SubscriptionRepository.disable_subscription(db, user_id)

            # Use centralized cache invalidation
            invalidate_subscription_caches(user_id)

            logger.info(f"Disabled subscription for user {user_id}")
            return success
    except Exception as e:
        logger.error(f"Error disabling subscription for user {user_id}: {e}")
        return False


def enable_subscription_for_user(user_id: int) -> bool:
    """
    Enable subscription for a user by setting is_paused to False in user_filters table

    Args:
        user_id: User's database ID

    Returns:
        True if successful, False otherwise
    """
    try:
        with db_session() as db:
            success = SubscriptionRepository.enable_subscription(db, user_id)

            # Use centralized cache invalidation
            invalidate_subscription_caches(user_id)

            logger.info(f"Enabled subscription for user {user_id}")
            return success
    except Exception as e:
        logger.error(f"Error enabling subscription for user {user_id}: {e}")
        return False


def count_subscriptions(user_id: int) -> int:
    """
    Count the number of subscriptions (filters) for a user

    Args:
        user_id: User's database ID

    Returns:
        Number of subscriptions
    """
    try:
        with db_session() as db:
            return SubscriptionRepository.count_subscriptions(db, user_id)
    except Exception as e:
        logger.error(f"Error counting subscriptions for user {user_id}: {e}")
        return 0


def list_subscriptions_paginated(user_id: int, page: int = 0, per_page: int = 5) -> list:
    """
    Get a paginated list of subscriptions for a user

    Args:
        user_id: User's database ID
        page: Page number (0-based)
        per_page: Number of items per page

    Returns:
        List of subscription dictionaries
    """
    try:
        with db_session() as db:
            return SubscriptionRepository.list_subscriptions_paginated(db, user_id, page, per_page)
    except Exception as e:
        logger.error(f"Error listing subscriptions for user {user_id}: {e}")
        return []


def get_subscription_status(user_id: int) -> dict:
    """
    Get subscription status data for a user with caching
    """
    # Try to get from cache using the cache manager
    cached_status = UserCacheManager.get_subscription_status(user_id)
    if cached_status:
        return cached_status

    try:
        with db_session() as db:
            user = UserRepository.get_by_id(db, user_id)

            if not user:
                return {"active": False}

            now = datetime.now()
            free_until = user.free_until
            subscription_until = user.subscription_until

            # Calculate if subscription is active
            free_active = free_until and free_until > now
            paid_active = subscription_until and subscription_until > now

            status = {
                "active": free_active or paid_active,
                "free_active": free_active,
                "paid_active": paid_active,
                "free_until": free_until.isoformat() if free_until else None,
                "subscription_until": subscription_until.isoformat() if subscription_until else None
            }

            # Cache the result using the cache manager
            UserCacheManager.set_subscription_status(user_id, status)

            return status
    except Exception as e:
        logger.error(f"Error getting subscription status for user {user_id}: {e}")
        return {"active": False, "error": str(e)}