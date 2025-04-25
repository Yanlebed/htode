# common/db/models.py
"""
Improved database models with batch queries and eager loading
"""
import time
import json
import decimal
import logging
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from datetime import datetime

from .database import execute_query
from .query_builder import QueryBuilder
from common.config import GEO_ID_MAPPING, get_key_by_value, REDIS_URL
from common.utils.phone_parser import extract_phone_numbers_from_resource
from common.utils.cache import redis_cache, CacheTTL, batch_get_cached, batch_set_cached, redis_client
from common.db.database import get_db_connection
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Batch size for operations to balance between network round trips and memory usage
BATCH_SIZE = 100


def get_or_create_user(messenger_id, messenger_type="telegram"):
    """
    Get or create a user with telegram_id, viber_id, or whatsapp_id
    """
    logger.info(f"Getting user with {messenger_type} id: {messenger_id}")

    if messenger_type == "telegram":
        sql_check = "SELECT id FROM users WHERE telegram_id = %s"
    elif messenger_type == "viber":
        sql_check = "SELECT id FROM users WHERE viber_id = %s"
    else:  # whatsapp
        sql_check = "SELECT id FROM users WHERE whatsapp_id = %s"

    row = execute_query(sql_check, [messenger_id], fetchone=True)
    if row:
        logger.info(f"Found user with {messenger_type} id: {messenger_id}")
        return row['id']

    logger.info(f"Creating user with {messenger_type} id: {messenger_id}")
    free_until = (datetime.now() + datetime.timedelta(days=7)).isoformat()

    if messenger_type == "telegram":
        sql_insert = """
                     INSERT INTO users (telegram_id, free_until)
                     VALUES (%s, %s) RETURNING id \
                     """
    elif messenger_type == "viber":
        sql_insert = """
                     INSERT INTO users (viber_id, free_until)
                     VALUES (%s, %s) RETURNING id \
                     """
    else:  # whatsapp
        sql_insert = """
                     INSERT INTO users (whatsapp_id, free_until)
                     VALUES (%s, %s) RETURNING id \
                     """

    user = execute_query(sql_insert, [messenger_id, free_until], fetchone=True, commit=True)
    return user['id']


def update_user_filter(user_id, filters):
    """
    Update filters for a user with cache invalidation
    """
    logger.info(f"Updating filters for user_id: {user_id}")

    # First verify user exists
    check_sql = "SELECT id FROM users WHERE id = %s"
    user_exists = execute_query(check_sql, [user_id], fetchone=True)
    if not user_exists:
        logger.error(f"Cannot update filters - user_id {user_id} does not exist in database")
        raise ValueError(f"User ID {user_id} does not exist")

    property_type = filters.get('property_type')
    city = filters.get('city')
    geo_id = get_key_by_value(city, GEO_ID_MAPPING)
    rooms_count = filters.get('rooms')  # List or None
    price_min = filters.get('price_min')
    price_max = filters.get('price_max')

    sql_upsert = """
                 INSERT INTO user_filters (user_id, property_type, city, rooms_count, price_min, price_max)
                 VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (user_id)
    DO
                 UPDATE SET
                     property_type = EXCLUDED.property_type,
                     city = EXCLUDED.city,
                     rooms_count = EXCLUDED.rooms_count,
                     price_min = EXCLUDED.price_min,
                     price_max = EXCLUDED.price_max \
                 """
    logger.info(
        f"Executing query with params: [{user_id}, {property_type}, {geo_id}, {rooms_count}, {price_min}, {price_max}]")
    execute_query(sql_upsert, [user_id, property_type, geo_id, rooms_count, price_min, price_max], commit=True)

    # Invalidate relevant cache entries
    cache_key = f"user_filters:{user_id}"
    redis_client.delete(cache_key)

    # Also invalidate the matching users cache for ads that might match this filter
    matching_pattern = "matching_users:*"
    matching_keys = redis_client.keys(matching_pattern)
    if matching_keys:
        redis_client.delete(*matching_keys)


@redis_cache("user_filters", ttl=CacheTTL.MEDIUM)
def get_user_filters(user_id):
    """Get user filters with caching"""
    sql = "SELECT * FROM user_filters WHERE user_id = %s"
    rows = execute_query(sql, [user_id], fetch=True)
    return rows[0] if rows else None


def batch_get_user_filters(user_ids):
    """
    Get filters for multiple users in a single query to prevent N+1 problems

    Args:
        user_ids: List of user IDs to fetch filters for

    Returns:
        Dict mapping user_id to their filters
    """
    if not user_ids:
        return {}

    # Try to get from cache first
    cache_keys = [f"user_filters:{user_id}" for user_id in user_ids]
    cached_results = batch_get_cached(user_ids, prefix="user_filters")

    # Identify which user_ids were not in cache
    missing_user_ids = [uid for uid in user_ids if uid not in cached_results]

    if not missing_user_ids:
        return cached_results

    # Fetch missing data from database in batches to avoid huge IN clauses
    results = dict(cached_results)  # Start with cached results

    for i in range(0, len(missing_user_ids), BATCH_SIZE):
        batch = missing_user_ids[i:i + BATCH_SIZE]

        # Build and execute query for this batch
        query = QueryBuilder("user_filters")
        query.where_in("user_id", batch)
        rows = query.execute(fetch=True)

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

    # Choose the appropriate SQL query based on messenger type
    if messenger_type == "telegram":
        sql = "SELECT id FROM users WHERE telegram_id = %s"
    elif messenger_type == "viber":
        sql = "SELECT id FROM users WHERE viber_id = %s"
    elif messenger_type == "whatsapp":
        sql = "SELECT id FROM users WHERE whatsapp_id = %s"
    else:
        logger.error(f"Invalid messenger type: {messenger_type}")
        return None

    # Execute the query
    row = execute_query(sql, [messenger_id], fetchone=True)

    if row:
        logger.info(f"Found database user ID {row['id']} for {messenger_type} ID: {messenger_id}")
        return row['id']

    logger.warning(f"No database user found for {messenger_type} ID: {messenger_id}")
    return None


def get_platform_ids_for_user(user_id: int) -> dict:
    """
    Get all messaging platform IDs for a user.

    Args:
        user_id: Database user ID

    Returns:
        Dictionary with platform IDs (telegram_id, viber_id, whatsapp_id)
    """
    sql = """
          SELECT telegram_id, viber_id, whatsapp_id
          FROM users
          WHERE id = %s
          """
    user = execute_query(sql, [user_id], fetchone=True)

    if not user:
        return {}

    # Create a cleaned dictionary with only non-None values
    platform_ids = {}
    if user.get("telegram_id") is not None:
        platform_ids["telegram_id"] = user["telegram_id"]

    if user.get("viber_id") is not None:
        platform_ids["viber_id"] = user["viber_id"]

    if user.get("whatsapp_id") is not None:
        platform_ids["whatsapp_id"] = user["whatsapp_id"]

    return platform_ids


def find_users_for_ad(ad):
    """
    Finds users whose subscription filters match this ad.
    Now with Redis caching and batch processing to improve performance.
    """
    try:
        # Create a cache key based on the ad's primary attributes that affect matching
        ad_id = ad.get('id')
        cache_key = f"matching_users:{ad_id}"

        # Try to get results from cache first
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f'Cache hit for ad {ad_id} matching users')
            return json.loads(cached)

        logger.info(f'Looking for users for ad: {ad}')

        # Improved SQL query with indexed columns first in WHERE conditions
        # and optimization for both active and free users
        sql = """
              SELECT u.id AS user_id
              FROM users u
                       JOIN user_filters uf ON u.id = uf.user_id
              WHERE (u.free_until > NOW() OR u.subscription_until > NOW())
                AND uf.is_paused = FALSE
                AND (uf.property_type = %s OR uf.property_type IS NULL)
                AND (uf.city = %s OR uf.city IS NULL)
                AND (
                  uf.rooms_count IS NULL
                      OR %s = ANY (uf.rooms_count)
                  )
                AND (uf.price_min IS NULL OR %s >= uf.price_min)
                AND (uf.price_max IS NULL OR %s <= uf.price_max)
              """

        # Extract ad properties for matching
        ad_property_type = ad.get('property_type')
        ad_city = ad.get('city')
        ad_rooms = ad.get('rooms_count')
        ad_price = ad.get('price')

        # Execute the SQL query
        rows = execute_query(sql, [ad_property_type, ad_city, ad_rooms, ad_price, ad_price], fetch=True)
        logger.info(f'Found {len(rows)} users for ad: {ad}')

        # Extract user IDs from results
        user_ids = [row["user_id"] for row in rows]

        # Cache the results for 1 hour
        # This is especially valuable since user filter preferences change infrequently
        redis_client.set(cache_key, json.dumps(user_ids), ex=CacheTTL.STANDARD)

        return user_ids
    except Exception as e:
        logger.error(f"Error finding users for ad {ad.get('id')}: {e}")
        return []  # Return empty list on error to avoid service disruption


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
    cache_key = f"user_subscription:{user_id}"
    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    sql = "SELECT * FROM user_filters WHERE user_id = %s"
    row = execute_query(sql, [user_id], fetchone=True)

    if row:
        # Cache for 5 minutes - this data changes infrequently but is accessed often
        redis_client.set(cache_key, json.dumps(row), ex=CacheTTL.MEDIUM)
        return row
    else:
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


def add_favorite_ad(user_id, ad_id):
    """Add a favorite ad with cache invalidation"""
    # check limit 50
    sql_count = "SELECT COUNT(*) as cnt FROM favorite_ads WHERE user_id = %s"
    row = execute_query(sql_count, [user_id], fetchone=True)
    if row["cnt"] >= 50:
        raise ValueError("You already have 50 favorite ads, cannot add more.")

    sql_insert = """
                 INSERT INTO favorite_ads (user_id, ad_id)
                 VALUES (%s, %s) ON CONFLICT (user_id, ad_id) DO NOTHING -- if you have unique constraint      \
                 """
    execute_query(sql_insert, [user_id, ad_id])

    # Invalidate favorites cache
    redis_client.delete(f"user_favorites:{user_id}")


def list_favorites(user_id):
    """List favorites with caching"""
    cache_key = f"user_favorites:{user_id}"
    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    # Use the optimized version with eager loading
    result = list_favorites_with_eager_loading(user_id)

    # Cache for 5 minutes - favorites change more frequently than filters
    redis_client.set(cache_key, json.dumps(result), ex=CacheTTL.MEDIUM)

    return result


def remove_favorite_ad(user_id, ad_id):
    """Remove a favorite ad with cache invalidation"""
    sql = "DELETE FROM favorite_ads WHERE user_id = %s AND ad_id = %s"
    execute_query(sql, [user_id, ad_id])

    # Invalidate favorites cache
    redis_client.delete(f"user_favorites:{user_id}")

    return True


def get_extra_images(resource_url):
    """Get extra images for an ad with caching"""
    cache_key = f"extra_images:{resource_url}"
    cached = redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    # First, look up the ad using resource_url
    sql = "SELECT id FROM ads WHERE resource_url = %s"
    ad = execute_query(sql, [resource_url], fetchone=True)
    if not ad:
        return []

    ad_id = ad["id"]
    sql_images = "SELECT image_url FROM ad_images WHERE ad_id = %s"
    rows = execute_query(sql_images, [ad_id], fetch=True)

    images = [row["image_url"] for row in rows] if rows else []

    # Cache for 1 hour - images rarely change
    redis_client.set(cache_key, json.dumps(images), ex=CacheTTL.LONG)

    return images


def get_full_ad_description(resource_url):
    """Get full ad description with caching"""
    cache_key = f"ad_description:{resource_url}"
    cached = redis_client.get(cache_key)

    if cached:
        return cached.decode('utf-8')

    logger.info(f'Getting full ad description for resource_url: {resource_url}...')
    sql = "SELECT description from ads WHERE resource_url = %s"
    ad = execute_query(sql, [resource_url], fetchone=True)

    description = ad["description"] if ad else None

    if description:
        # Cache for 1 hour - descriptions rarely change
        redis_client.set(cache_key, description, ex=CacheTTL.LONG)

    return description


def store_ad_phones(resource_url, ad_id):
    """
    Extracts phone numbers and stores them with cache invalidation
    """
    # First check if the ad exists in the database
    check_sql = "SELECT id FROM ads WHERE id = %s"
    ad_exists = execute_query(check_sql, [ad_id], fetchone=True)

    if not ad_exists:
        logger.warning(f"Cannot store phones for ad_id={ad_id} - ad doesn't exist in the database")
        return 0

    # Only proceed if the ad exists
    try:
        phones_added = 0
        result = extract_phone_numbers_from_resource(resource_url)
        phones = result.phone_numbers
        viber_link = result.viber_link

        # Begin transaction for all phone operations
        conn = None
        try:
            # Use a context manager approach
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Delete existing phones for this ad to avoid duplicates
                    cur.execute("DELETE FROM ad_phones WHERE ad_id = %s", [ad_id])

                    # Insert new phones
                    for phone in phones:
                        cur.execute(
                            "INSERT INTO ad_phones (ad_id, phone) VALUES (%s, %s)",
                            [ad_id, phone]
                        )
                        phones_added += 1

                    # Insert viber link if available
                    if viber_link:
                        cur.execute(
                            "INSERT INTO ad_phones (ad_id, viber_link) VALUES (%s, %s)",
                            [ad_id, viber_link]
                        )

                    conn.commit()

                    # Invalidate relevant cache
                    redis_client.delete(f"full_ad:{ad_id}")

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Transaction error storing phones for ad {ad_id}: {e}")
            raise

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

    # Prefetch user filters
    filters = get_user_filters(user_id)

    # Prefetch user's favorites
    favorites = list_favorites(user_id)

    # Prefetch subscription data
    subscription = get_subscription_data_for_user(user_id)

    # If we have favorites, prefetch full data for those ads
    if favorites:
        ad_ids = [fav.get('ad_id') for fav in favorites if fav.get('ad_id')]
        batch_get_full_ad_data(ad_ids)

    logger.info(f"Cache warmed for user_id: {user_id}")
