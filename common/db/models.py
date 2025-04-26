# common/db/models.py
"""
Improved database models with batch queries and eager loading
"""
import json
import decimal
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from common.db.models import AdPhone, Ad
from .database import execute_query
from common.config import GEO_ID_MAPPING, get_key_by_value
from common.utils.phone_parser import extract_phone_numbers_from_resource
from common.utils.cache import redis_cache, CacheTTL, batch_get_cached, batch_set_cached, redis_client
from common.db.database import get_db_connection
from psycopg2.extras import RealDictCursor

from common.db.repositories.user_repository import UserRepository
from common.db.session import db_session
from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.repositories.ad_repository import AdRepository
from common.db.repositories.favorite_repository import FavoriteRepository

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
        from datetime import datetime, timedelta
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
            SubscriptionRepository.update_user_filter(db, user_id, filter_data)

            logger.info(
                f"Updated filters: [{user_id}, {property_type}, {geo_id}, {rooms_count}, {price_min}, {price_max}]")

            # Invalidate relevant cache entries
            from common.utils.cache import redis_client
            cache_key = f"user_filters:{user_id}"
            redis_client.delete(cache_key)

            # Also invalidate the matching users cache for ads that might match this filter
            matching_pattern = "matching_users:*"
            matching_keys = redis_client.keys(matching_pattern)
            if matching_keys:
                redis_client.delete(*matching_keys)

    except Exception as e:
        logger.error(f"Error updating user filters: {e}")
        raise


@redis_cache("user_filters", ttl=CacheTTL.MEDIUM)
def get_user_filters(user_id):
    """Get user filters with caching"""
    sql = "SELECT * FROM user_filters WHERE user_id = %s"
    rows = execute_query(sql, [user_id], fetch=True)
    return rows[0] if rows else None


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

    for i in range(0, len(missing_user_ids), BATCH_SIZE):
        batch = missing_user_ids[i:i + BATCH_SIZE]

        placeholders = ','.join(['%s'] * len(batch))
        sql = f"SELECT * FROM user_filters WHERE user_id IN ({placeholders})"
        rows = execute_query(sql, batch, fetch=True)

        # Process results
        batch_results = {}
        for row in rows:
            user_id = row['user_id']
            results[user_id] = row
            batch_results[user_id] = row

        # Cache the batch results
        batch_set_cached(batch_results, ttl=CacheTTL.MEDIUM, prefix="user_filters")

    return results


def get_db_user_id_by_telegram_id(messenger_id, messenger_type="telegram"):
    """
    Get database user ID from messenger-specific ID (telegram_id, viber_id, or whatsapp_id).

    Args:
        messenger_id: Platform-specific user ID (telegram_id, viber_id, or whatsapp_id)
        messenger_type: Type of messenger ("telegram", "viber", or "whatsapp")

    Returns:
        Database user ID or None if not found
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
        from common.utils.cache import redis_client

        cache_key = f"matching_users:{ad_id}"

        # Try to get results from cache first
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f'Cache hit for ad {ad_id} matching users')
            return json.loads(cached)

        logger.info(f'Looking for users for ad: {ad}')

        with db_session() as db:
            # Convert dict to Ad object if needed
            if isinstance(ad, dict):
                existing_ad = db.query(Ad).get(ad_id)
                if not existing_ad:
                    # Create temporary Ad object for matching
                    from common.db.models.ad import Ad
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
    # Since each ad has unique matching criteria, we still need to process them individually
    # But we can optimize how we fetch and process the user filters

    # First, get all active users
    active_users_sql = """
                       SELECT id \
                       FROM users
                       WHERE free_until > NOW() \
                          OR subscription_until > NOW() \
                       """
    active_users = execute_query(active_users_sql, fetch=True)
    active_user_ids = [row['id'] for row in active_users]

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

        # Extract ad properties for matching
        ad_property_type = ad.get('property_type')
        ad_city = ad.get('city')
        ad_rooms = ad.get('rooms_count')
        ad_price = ad.get('price')

        matching_users = []

        # Check each user's filters against this ad
        for user_id, filters in user_filters.items():
            if filters.get('is_paused', False):
                continue

            # Check property type match
            if filters.get('property_type') and filters['property_type'] != ad_property_type:
                continue

            # Check city match
            if filters.get('city') and filters['city'] != ad_city:
                continue

            # Check rooms match
            if filters.get('rooms_count') and ad_rooms not in filters['rooms_count']:
                continue

            # Check price range
            if filters.get('price_min') and ad_price < filters['price_min']:
                continue

            if filters.get('price_max') and ad_price > filters['price_max']:
                continue

            # All criteria matched
            matching_users.append(user_id)

        # Store results and cache them
        results[ad_id] = matching_users
        redis_client.set(f"matching_users:{ad_id}", json.dumps(matching_users), ex=CacheTTL.STANDARD)

    # Combine cached and newly processed results
    results.update(cached_results)
    return results


def get_subscription_data_for_user(user_id):
    """Get subscription data for a user with caching"""
    from common.utils.cache import redis_client

    cache_key = f"user_subscription:{user_id}"
    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    try:
        with db_session() as db:
            user_filter = SubscriptionRepository.get_user_filters(db, user_id)

            if user_filter:
                # Cache for 5 minutes - this data changes infrequently but is accessed often
                redis_client.set(cache_key, json.dumps(user_filter), ex=300)
                return user_filter
            else:
                return None
    except Exception as e:
        logger.error(f"Error getting subscription data for user {user_id}: {e}")
        return None


def get_full_ad_data(ad_id):
    """Get complete ad data with joined images and phones (with caching)"""
    cache_key = f"full_ad:{ad_id}"

    # Try to get from cache
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Database query with multiple joins and eager loading
    sql = """
          SELECT a.*,
                 array_agg(DISTINCT ai.image_url) as images,
                 array_agg(DISTINCT ap.phone)     as phones,
                 ap.viber_link
          FROM ads a
                   LEFT JOIN ad_images ai ON a.id = ai.ad_id
                   LEFT JOIN ad_phones ap ON a.id = ap.ad_id
          WHERE a.id = %s
          GROUP BY a.id, ap.viber_link \
          """

    ad_data = execute_query(sql, [ad_id], fetchone=True)

    if ad_data:
        # Convert to JSON serializable directly
        serializable_ad_data = {}
        for key, value in ad_data.items():
            if isinstance(value, decimal.Decimal):
                serializable_ad_data[key] = float(value)
            elif isinstance(value, datetime) or isinstance(value, datetime.date):
                serializable_ad_data[key] = value.isoformat()
            else:
                serializable_ad_data[key] = value

        # Cache for 30 minutes
        redis_client.set(cache_key, json.dumps(serializable_ad_data), ex=CacheTTL.MEDIUM)
        return serializable_ad_data

    return None


def batch_get_full_ad_data(ad_ids):
    """
    Get complete data for multiple ads in a single query

    Args:
        ad_ids: List of ad IDs

    Returns:
        Dict mapping ad_id to ad data
    """
    if not ad_ids:
        return {}

    # Try to get from cache first
    cache_keys = [f"full_ad:{ad_id}" for ad_id in ad_ids]
    cached_results = {}

    pipeline = redis_client.pipeline()
    for key in cache_keys:
        pipeline.get(key)
    cached_values = pipeline.execute()

    for i, value in enumerate(cached_values):
        if value:
            ad_id = ad_ids[i]
            cached_results[ad_id] = json.loads(value)

    # Identify which ads were not in cache
    cached_ad_ids = set(cached_results.keys())
    missing_ad_ids = [ad_id for ad_id in ad_ids if ad_id not in cached_ad_ids]

    if not missing_ad_ids:
        return cached_results

    # Process batches of missing ads
    results = dict(cached_results)  # Start with cached results

    for i in range(0, len(missing_ad_ids), BATCH_SIZE):
        batch = missing_ad_ids[i:i + BATCH_SIZE]

        # Using a single optimized query with array_agg to get all joined data at once
        sql = """
              SELECT a.*,
                     array_agg(DISTINCT ai.image_url) as images,
                     array_agg(DISTINCT ap.phone)     as phones,
                     ap.viber_link,
                     a.id                             as ad_id
              FROM ads a
                       LEFT JOIN ad_images ai ON a.id = ai.ad_id
                       LEFT JOIN ad_phones ap ON a.id = ap.ad_id
              WHERE a.id = ANY (%s)
              GROUP BY a.id, ap.viber_link
              """

        rows = execute_query(sql, [batch], fetch=True)

        # Process results and cache them
        for row in rows:
            ad_id = row.get('ad_id')

            # Convert to JSON serializable format
            serializable_data = {}
            for key, value in row.items():
                if isinstance(value, decimal.Decimal):
                    serializable_data[key] = float(value)
                elif isinstance(value, datetime) or isinstance(value, datetime.date):
                    serializable_data[key] = value.isoformat()
                else:
                    serializable_data[key] = value

            results[ad_id] = serializable_data

            # Cache individual results
            redis_client.set(f"full_ad:{ad_id}", json.dumps(serializable_data), ex=CacheTTL.MEDIUM)

    return results


def list_favorites_with_eager_loading(user_id):
    """
    List user's favorite ads with eager loading of related data
    This prevents N+1 query problems by loading all related data in a single query
    """
    sql = """
          SELECT fa.id,
                 fa.ad_id,
                 ads.price,
                 ads.address,
                 ads.city,
                 ads.property_type,
                 ads.rooms_count,
                 ads.resource_url,
                 ads.external_id,
                 ads.square_feet,
                 ads.floor,
                 ads.total_floors,
                 array_agg(DISTINCT ai.image_url) as images,
                 array_agg(DISTINCT ap.phone)     as phones,
                 ap.viber_link
          FROM favorite_ads fa
                   JOIN ads ON fa.ad_id = ads.id
                   LEFT JOIN ad_images ai ON ads.id = ai.ad_id
                   LEFT JOIN ad_phones ap ON ads.id = ap.ad_id
          WHERE fa.user_id = %s
          GROUP BY fa.id, ads.price, ads.address, ads.city, ads.property_type,
                   ads.rooms_count, ads.resource_url, ads.external_id, ads.square_feet,
                   ads.floor, ads.total_floors, ap.viber_link
          ORDER BY fa.created_at DESC \
          """

    results = execute_query(sql, [user_id], fetch=True)

    # Convert decimal values for JSON serialization
    for result in results:
        for key, value in result.items():
            if isinstance(value, decimal.Decimal):
                result[key] = float(value)
            elif isinstance(value, datetime) or isinstance(value, datetime.date):
                result[key] = value.isoformat()

    return results


def add_subscription(user_id, property_type, city_id, rooms_count, price_min, price_max):
    """
    Adds a new subscription row for this user with cache invalidation.
    We assume you already checked that the user doesn't exceed 20 subscriptions.
    """
    # First, ensure the user has < 20
    sql_count = "SELECT COUNT(*) as cnt FROM user_filters WHERE user_id = %s"
    row = execute_query(sql_count, [user_id], fetchone=True)
    if row["cnt"] >= 20:
        raise ValueError("You already have 20 subscriptions, cannot add more.")

    sql_insert = """
                 INSERT INTO user_filters (user_id, property_type, city, rooms_count, price_min, price_max)
                 VALUES (%s, %s, %s, %s, %s, %s) RETURNING id \
                 """
    sub = execute_query(sql_insert, [user_id, property_type, city_id, rooms_count, price_min, price_max], fetchone=True)

    # Invalidate the user_filters cache
    redis_client.delete(f"user_filters:{user_id}")

    # Invalidate matching users cache for all ads since filter changes might affect matching
    matching_keys = redis_client.keys("matching_users:*")
    if matching_keys:
        redis_client.delete(*matching_keys)

    return sub["id"]


def list_subscriptions(user_id):
    """List user subscriptions with caching"""
    cache_key = f"user_subscriptions_list:{user_id}"
    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    sql = """
          SELECT id, property_type, city, rooms_count, price_min, price_max
          FROM user_filters
          WHERE user_id = %s
          ORDER BY id \
          """
    result = execute_query(sql, [user_id], fetch=True)

    # Convert for JSON serialization
    serializable_result = []
    for row in result:
        serializable_row = {}
        for key, value in row.items():
            if isinstance(value, decimal.Decimal):
                serializable_row[key] = float(value)
            else:
                serializable_row[key] = value
        serializable_result.append(serializable_row)

    # Cache for 5 minutes
    redis_client.set(cache_key, json.dumps(serializable_result), ex=CacheTTL.MEDIUM)

    return serializable_result


def remove_subscription(subscription_id, user_id):
    """
    Remove a subscription with cache invalidation
    """
    sql = "DELETE FROM user_filters WHERE id = %s AND user_id = %s"
    execute_query(sql, [subscription_id, user_id])

    # Invalidate relevant cache entries
    redis_client.delete(f"user_filters:{user_id}")
    redis_client.delete(f"user_subscriptions_list:{user_id}")

    # Invalidate matching_users cache as filter changes might affect matching
    matching_keys = redis_client.keys("matching_users:*")
    if matching_keys:
        redis_client.delete(*matching_keys)


def update_subscription(subscription_id, user_id, new_values):
    """
    Update a subscription with cache invalidation
    """
    sql = """
          UPDATE user_filters
          SET property_type = %s,
              city          = %s,
              rooms_count   = %s,
              price_min     = %s,
              price_max     = %s
          WHERE id = %s
            AND user_id = %s \
          """
    params = [new_values['property_type'], new_values['city'],
              new_values['rooms_count'], new_values['price_min'], new_values['price_max'],
              subscription_id, user_id]
    execute_query(sql, params)

    # Invalidate relevant cache entries
    redis_client.delete(f"user_filters:{user_id}")
    redis_client.delete(f"user_subscriptions_list:{user_id}")

    # Invalidate matching_users cache
    matching_keys = redis_client.keys("matching_users:*")
    if matching_keys:
        redis_client.delete(*matching_keys)


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

            # Invalidate favorites cache
            from common.utils.cache import redis_client
            redis_client.delete(f"user_favorites:{user_id}")

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
    from common.utils.cache import redis_client

    cache_key = f"user_favorites:{user_id}"
    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    try:
        with db_session() as db:
            favorites = FavoriteRepository.list_favorites(db, user_id)

            # Cache for 5 minutes - favorites change more frequently than filters
            redis_client.set(cache_key, json.dumps(favorites), ex=300)

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

            # Invalidate favorites cache
            from common.utils.cache import redis_client
            redis_client.delete(f"user_favorites:{user_id}")

            return success
    except Exception as e:
        logger.error(f"Error removing favorite ad: {e}")
        return False


def get_extra_images(resource_url):
    """Get extra images for an ad with caching"""
    from common.utils.cache import redis_client

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
    from common.utils.cache import redis_client

    cache_key = f"ad_description:{resource_url}"
    cached = redis_client.get(cache_key)

    if cached:
        return cached.decode('utf-8')

    logger.info(f'Getting full ad description for resource_url: {resource_url}...')

    try:
        with db_session() as db:
            ad = AdRepository.get_by_resource_url(db, resource_url)
            description = ad.description if ad else None

        if description:
            # Cache for 1 hour - descriptions rarely change
            redis_client.set(cache_key, description, ex=3600)

        return description
    except Exception as e:
        logger.error(f"Error getting full ad description: {e}")
        return None


def store_ad_phones(resource_url, ad_id):
    """
    Extracts phone numbers and stores them with cache invalidation
    """
    try:
        with db_session() as db:
            # First check if the ad exists in the database
            ad = db.query(Ad).get(ad_id)

            if not ad:
                logger.warning(f"Cannot store phones for ad_id={ad_id} - ad doesn't exist in the database")
                return 0

            # Extract phones from resource
            result = extract_phone_numbers_from_resource(resource_url)
            phones = result.phone_numbers
            viber_link = result.viber_link

            # Delete existing phones for this ad to avoid duplicates
            # This could be added to the AdRepository if not already there
            db.query(AdPhone).filter(AdPhone.ad_id == ad_id).delete()

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

            # Invalidate relevant cache
            from common.utils.cache import redis_client
            redis_client.delete(f"full_ad:{ad_id}")

            return phones_added
    except Exception as e:
        logger.error(f"Error extracting or storing phones for ad {ad_id}: {e}")
        return 0


def warm_cache_for_user(user_id):
    """
    Warm up cache for a user's most commonly accessed data
    Call this when user logs in or starts interacting with the system
    """
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

            with db_session() as db:
                for ad_id in ad_ids:
                    AdRepository.get_full_ad_data(db, ad_id)

        logger.info(f"Cache warmed for user_id: {user_id}")
    except Exception as e:
        logger.error(f"Error warming cache for user {user_id}: {e}")


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

        # Invalidate cache
        from common.utils.cache import redis_client
        cache_key = f"user_subscription:{user_id}"
        redis_client.delete(cache_key)

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
    from common.utils.cache import redis_client

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
    Get all images associated with an ad.

    Args:
        ad_id: Either the database ID of the ad or the ad dictionary with an 'id' key

    Returns:
        List of image URLs
    """
    try:
        # Handle either an ad dict or direct ad_id
        if isinstance(ad_id, dict):
            ad_id = ad_id.get('id')

        if not ad_id:
            return []

        # Cache key for this query
        cache_key = f"ad_images:{ad_id}"
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)

        # Query database for images
        sql = "SELECT image_url FROM ad_images WHERE ad_id = %s"
        rows = execute_query(sql, [ad_id], fetch=True)

        if rows:
            urls = [row["image_url"] for row in rows]
            # Cache for 1 hour (images rarely change)
            redis_client.set(cache_key, json.dumps(urls), ex=3600)
            return urls

        return []
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

            # Invalidate relevant cache entries
            from common.utils.cache import redis_client
            cache_key = f"user_filters:{user_id}"
            redis_client.delete(cache_key)

            # Also invalidate matching users cache for ads
            matching_pattern = "matching_users:*"
            matching_keys = redis_client.keys(matching_pattern)
            if matching_keys:
                redis_client.delete(*matching_keys)

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

            # Invalidate relevant cache entries
            from common.utils.cache import redis_client
            cache_key = f"user_filters:{user_id}"
            redis_client.delete(cache_key)

            # Also invalidate matching users cache for ads
            matching_pattern = "matching_users:*"
            matching_keys = redis_client.keys(matching_pattern)
            if matching_keys:
                redis_client.delete(*matching_keys)

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


# Cache helper for subscription data
@redis_cache("subscription_status", ttl=CacheTTL.MEDIUM)  # 5 minutes cache
def get_subscription_status(user_id: int) -> dict:
    """
    Get subscription status data for a user with caching

    Args:
        user_id: User's database ID

    Returns:
        Dictionary with subscription status info
    """
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

            return {
                "active": free_active or paid_active,
                "free_active": free_active,
                "paid_active": paid_active,
                "free_until": free_until.isoformat() if free_until else None,
                "subscription_until": subscription_until.isoformat() if subscription_until else None
            }
    except Exception as e:
        logger.error(f"Error getting subscription status for user {user_id}: {e}")
        return {"active": False, "error": str(e)}