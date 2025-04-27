# system/maintenance.py

import logging
import time
import json
from datetime import datetime
from typing import List, Tuple, Dict, Any

from common.celery_app import celery_app
from common.db.database import execute_query, get_db_connection
from common.db.models import Ad
from common.db.session import db_session
from common.utils.s3_utils import delete_s3_image
from common.utils.unified_request_utils import make_request
from common.utils.cache import redis_client, CacheTTL
from common.config import GEO_ID_MAPPING
from common.services.ad_service import AdService
from common.services.user_service import UserService

logger = logging.getLogger(__name__)


@celery_app.task(name='system.maintenance.check_expiring_subscriptions')
def check_expiring_subscriptions() -> Dict[str, Any]:
    """
    Check for expiring subscriptions and send reminders.
    """
    start_time = time.time()

    try:
        with db_session() as db:
            results = UserService.check_expiring_subscriptions(db)

        execution_time = time.time() - start_time
        logger.info(f"Checked expiring subscriptions in {execution_time:.2f} seconds")

        return {
            "status": "success",
            "reminders_sent": results["reminders_sent"],
            "execution_time_seconds": execution_time
        }
    except Exception as e:
        logger.error(f"Error checking expiring subscriptions: {e}")
        return {
            "status": "error",
            "error": str(e),
            "execution_time_seconds": time.time() - start_time
        }


@celery_app.task(name='system.maintenance.cleanup_old_ads')
def cleanup_old_ads(days_old: int = 30, check_activity: bool = True) -> Dict[str, Any]:
    """
    Cleans up ads that are older than the specified number of days,
    and optionally checks if they are still active (not 404).

    Args:
        days_old: Number of days after which ads are considered old
        check_activity: Whether to check if the ad is still active (not 404)

    Returns:
        Summary of cleanup operations with counts of deleted ads and images
    """
    logger.info(f"Starting cleanup of ads older than {days_old} days (check_activity={check_activity})")
    start_time = time.time()

    try:
        with db_session() as db:
            deleted_count, images_deleted_count = AdService.cleanup_old_ads(db, days_old, check_activity)

        execution_time = time.time() - start_time
        logger.info(
            f"Cleanup completed in {execution_time:.2f} seconds. "
            f"Deleted: {deleted_count}, Images deleted: {images_deleted_count}"
        )

        return {
            "status": "completed",
            "ads_deleted": deleted_count,
            "images_deleted": images_deleted_count,
            "execution_time_seconds": execution_time
        }
    except Exception as e:
        logger.error(f"Error in cleanup_old_ads: {e}")
        return {
            "status": "error",
            "error": str(e),
            "execution_time_seconds": time.time() - start_time
        }


def get_old_ads_for_cleanup(cutoff_date: datetime) -> List[Ad]:
    with db_session() as db:
        return db.query(Ad).filter(Ad.insert_time < cutoff_date).all()


def process_ads_batch(batch: List[Dict[str, Any]], check_activity: bool) -> Tuple[int, int, int]:
    """
    Process a batch of ads, checking if they're inactive and deleting if necessary.

    Args:
        batch: List of ads to process
        check_activity: Whether to check if ads are active before deleting

    Returns:
        Tuple of (number of ads deleted, number of images deleted, number of ads checked)
    """
    deleted_count = 0
    images_deleted_count = 0
    checked_count = 0

    for ad in batch:
        checked_count += 1
        ad_id = ad.get('id')
        resource_url = ad.get('resource_url')

        # Skip ads without proper data
        if not ad_id or not resource_url:
            logger.warning(f"Skipping ad with incomplete data: {ad}")
            continue

        should_delete = True

        # Check if ad is still active by making a HEAD request
        if check_activity:
            if is_ad_inactive(resource_url):
                logger.info(f"Ad {ad_id} is inactive (URL: {resource_url})")
            else:
                # Ad is still active, don't delete
                should_delete = False
                logger.debug(f"Ad {ad_id} is still active, skipping")

        if should_delete:
            # Get images before deleting the ad
            images = get_ad_images(ad_id)

            # Delete the ad and related data
            deleted = delete_ad(ad_id)

            if deleted:
                deleted_count += 1

                # Delete images from S3
                for image_url in images:
                    if delete_s3_image(image_url):
                        images_deleted_count += 1
                    else:
                        logger.warning(f"Failed to delete image: {image_url}")

                # Clear cache for the deleted ad
                clear_ad_cache(ad_id, resource_url)

    return deleted_count, images_deleted_count, checked_count


def is_ad_inactive(resource_url: str) -> bool:
    """
    Check if an ad is inactive (returns 404 or other error status).

    Args:
        resource_url: URL of the ad to check

    Returns:
        True if the ad is inactive, False otherwise
    """
    try:
        # Use a HEAD request to minimize data transfer
        response = make_request(
            url=resource_url,
            method='head',
            timeout=10,
            retries=2,
            raise_for_status=False
        )

        # Consider non-existent or error responses as inactive
        if not response or response.status_code >= 400:
            return True

        return False
    except Exception as e:
        logger.warning(f"Error checking ad activity for {resource_url}: {e}")
        # Consider ads with connection errors as inactive
        return True


def get_ad_images(ad_id: int) -> List[str]:
    """
    Get all image URLs for an ad.

    Args:
        ad_id: ID of the ad

    Returns:
        List of image URLs
    """
    sql = "SELECT image_url FROM ad_images WHERE ad_id = %s"
    rows = execute_query(sql, [ad_id], fetch=True)

    if not rows:
        return []

    return [row.get('image_url') for row in rows if row.get('image_url')]


def delete_ad(ad_id: int) -> bool:
    """
    Delete an ad and all its related data (images, phones, favorites) using transaction.

    Args:
        ad_id: ID of the ad to delete

    Returns:
        True if the ad was deleted successfully, False otherwise
    """
    try:
        # Use a transaction to ensure atomic deletion
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    # Start transaction
                    cursor.execute("BEGIN")

                    # Delete from favorite_ads
                    cursor.execute("DELETE FROM favorite_ads WHERE ad_id = %s", [ad_id])

                    # Delete from ad_phones
                    cursor.execute("DELETE FROM ad_phones WHERE ad_id = %s", [ad_id])

                    # Delete from ad_images
                    cursor.execute("DELETE FROM ad_images WHERE ad_id = %s", [ad_id])

                    # Finally delete the ad itself
                    cursor.execute("DELETE FROM ads WHERE id = %s", [ad_id])

                    # Commit the transaction
                    conn.commit()

                    logger.info(f"Successfully deleted ad {ad_id} and related data")
                    return True
                except Exception as e:
                    # Rollback on error
                    conn.rollback()
                    logger.error(f"Transaction error deleting ad {ad_id}: {e}")
                    return False
    except Exception as e:
        logger.error(f"Error getting connection to delete ad {ad_id}: {e}")
        return False


def clear_ad_cache(ad_id: int, resource_url: str = None):
    """
    Clear all cache entries related to a specific ad

    Args:
        ad_id: ID of the ad
        resource_url: Optional resource URL for additional cache keys
    """
    keys_to_delete = [
        f"full_ad:{ad_id}",
        f"matching_users:{ad_id}"
    ]

    if resource_url:
        keys_to_delete.extend([
            f"extra_images:{resource_url}",
            f"ad_description:{resource_url}"
        ])

    # Delete all keys that exist
    existing_keys = [key for key in keys_to_delete if redis_client.exists(key)]
    if existing_keys:
        redis_client.delete(*existing_keys)
        logger.debug(f"Cleared {len(existing_keys)} cache keys for ad {ad_id}")


@celery_app.task(name='system.maintenance.cleanup_expired_verification_codes')
def cleanup_expired_verification_codes() -> Dict[str, int]:
    """
    Clean up expired verification codes and tokens.

    Returns:
        Dictionary with counts of deleted items
    """
    # Cleanup verification codes
    codes_sql = "DELETE FROM verification_codes WHERE expires_at < NOW()"
    codes_result = execute_query(codes_sql)

    # Cleanup email verification tokens
    tokens_sql = "DELETE FROM email_verification_tokens WHERE expires_at < NOW()"
    tokens_result = execute_query(tokens_sql)

    logger.info("Cleaned up expired verification codes and tokens")
    return {
        "verification_codes_deleted": codes_result.rowcount if hasattr(codes_result, 'rowcount') else 0,
        "email_tokens_deleted": tokens_result.rowcount if hasattr(tokens_result, 'rowcount') else 0
    }


@celery_app.task(name='system.maintenance.cleanup_redis_cache')
def cleanup_redis_cache(pattern: str = None, older_than_days: int = None) -> Dict[str, int]:
    """
    Clean up Redis cache entries matching a pattern and/or older than specified days

    Args:
        pattern: Optional Redis key pattern to match (e.g., "user_filters:*")
        older_than_days: Optional age threshold in days

    Returns:
        Dictionary with count of deleted cache entries
    """
    start_time = time.time()
    deleted_count = 0

    if not pattern:
        # Use a generic pattern to match all cache keys
        pattern = "*"

    # Get all keys matching the pattern
    matching_keys = redis_client.keys(pattern)
    logger.info(f"Found {len(matching_keys)} keys matching pattern: {pattern}")

    if not matching_keys:
        return {"deleted_count": 0, "execution_time_seconds": time.time() - start_time}

    if older_than_days is not None:
        # Only delete keys older than the specified threshold
        keys_to_delete = []

        # Use pipeline for efficiency
        pipe = redis_client.pipeline()
        for key in matching_keys:
            pipe.ttl(key)
        ttls = pipe.execute()

        # Calculate which keys to delete based on TTL
        for i, key in enumerate(matching_keys):
            ttl = ttls[i]

            # If TTL is -1 (no expiration) or -2 (key doesn't exist), skip
            if ttl < 0:
                continue

            # Calculate original TTL based on remaining TTL
            max_ttl = CacheTTL.EXTENDED  # Assume 7 days as maximum TTL
            age_seconds = max_ttl - ttl
            age_days = age_seconds / 86400  # Convert to days

            if age_days > older_than_days:
                keys_to_delete.append(key)

        if keys_to_delete:
            redis_client.delete(*keys_to_delete)
            deleted_count = len(keys_to_delete)
    else:
        # Delete all matching keys
        redis_client.delete(*matching_keys)
        deleted_count = len(matching_keys)

    execution_time = time.time() - start_time
    logger.info(f"Deleted {deleted_count} cache keys in {execution_time:.2f} seconds")

    return {
        "deleted_count": deleted_count,
        "execution_time_seconds": execution_time
    }


@celery_app.task(name='system.maintenance.optimize_database')
def optimize_database() -> Dict[str, Any]:
    """
    Perform database maintenance tasks like VACUUM and ANALYZE to optimize performance

    Returns:
        Dictionary with operation status
    """
    start_time = time.time()
    operations = []

    try:
        # List of tables to optimize
        tables = [
            "ads", "ad_images", "ad_phones", "users",
            "user_filters", "favorite_ads", "verification_codes",
            "email_verification_tokens", "payment_orders", "payment_history"
        ]

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Turn off auto-commit for these operations
                conn.autocommit = True

                # VACUUM ANALYZE on each table
                for table in tables:
                    logger.info(f"Running VACUUM ANALYZE on {table}")
                    cursor.execute(f"VACUUM ANALYZE {table}")
                    operations.append(f"VACUUM ANALYZE {table}")

                # Update table statistics
                for table in tables:
                    logger.info(f"Running ANALYZE on {table}")
                    cursor.execute(f"ANALYZE {table}")
                    operations.append(f"ANALYZE {table}")

                # Optimize indexes
                logger.info("Reindexing tables")
                cursor.execute("REINDEX DATABASE current_database()")
                operations.append("REINDEX DATABASE")

                # Reset auto-commit to default
                conn.autocommit = False

    except Exception as e:
        logger.error(f"Error during database optimization: {e}")
        return {
            "status": "error",
            "error": str(e),
            "execution_time_seconds": time.time() - start_time
        }

    execution_time = time.time() - start_time
    logger.info(f"Database optimization completed in {execution_time:.2f} seconds")

    return {
        "status": "success",
        "operations": operations,
        "execution_time_seconds": execution_time
    }


@celery_app.task(name='system.maintenance.cache_warming')
def cache_warming() -> Dict[str, int]:
    """
    Warm up cache for frequently accessed data

    Returns:
        Dictionary with count of items cached
    """
    start_time = time.time()
    cached_items = 0

    try:
        # 1. Warm up cache for active cities
        sql_cities = """
                     SELECT DISTINCT uf.city
                     FROM user_filters uf
                              JOIN users u ON uf.user_id = u.id
                     WHERE uf.city IS NOT NULL
                       AND (u.subscription_until > NOW() OR u.free_until > NOW()) \
                     """
        cities = execute_query(sql_cities, fetch=True)
        if cities:
            city_ids = [city['city'] for city in cities if city.get('city')]

            # Cache city data
            for city_id in city_ids:
                city_key = f"city:{city_id}"
                redis_client.set(city_key, json.dumps({
                    "id": city_id,
                    "name": GEO_ID_MAPPING.get(city_id, "Unknown")
                }), ex=CacheTTL.LONG)  # City data rarely changes
                cached_items += 1

        # 2. Warm up cache for most viewed ads
        sql_top_ads = """
                      SELECT ad_id, COUNT(*) as view_count
                      FROM (SELECT fa.ad_id \
                            FROM favorite_ads fa \
                            ORDER BY fa.created_at DESC LIMIT 1000) as recent_views
                      GROUP BY ad_id
                      ORDER BY view_count DESC LIMIT 50 \
                      """
        top_ads = execute_query(sql_top_ads, fetch=True)
        if top_ads:
            ad_ids = [ad['ad_id'] for ad in top_ads if ad.get('ad_id')]

            # Batch fetch ad data
            from common.db.models import batch_get_full_ad_data
            batch_get_full_ad_data(ad_ids)
            cached_items += len(ad_ids)

        # 3. Warm up cache for active users
        sql_active_users = """
                           SELECT id
                           FROM users
                           WHERE last_active > NOW() - interval '7 days'
                               LIMIT 100 \
                           """
        active_users = execute_query(sql_active_users, fetch=True)
        if active_users:
            user_ids = [user['id'] for user in active_users if user.get('id')]

            # Batch fetch user filters
            from common.db.models import batch_get_user_filters
            batch_get_user_filters(user_ids)
            cached_items += len(user_ids)

    except Exception as e:
        logger.error(f"Error during cache warming: {e}")
        return {
            "status": "error",
            "error": str(e),
            "cached_items": cached_items,
            "execution_time_seconds": time.time() - start_time
        }

    execution_time = time.time() - start_time
    logger.info(f"Cache warming completed in {execution_time:.2f} seconds, cached {cached_items} items")

    return {
        "status": "success",
        "cached_items": cached_items,
        "execution_time_seconds": execution_time
    }


@celery_app.task(name='system.maintenance.check_database_connections')
def check_database_connections() -> Dict[str, Any]:
    """
    Check database connection pool health and reset if necessary

    Returns:
        Dictionary with pool statistics
    """
    from common.db.database import pool, initialize_pool

    if not pool:
        logger.warning("Database connection pool not initialized, initializing now")
        initialize_pool()
        return {
            "status": "initialized",
            "min_connections": pool.minconn,
            "max_connections": pool.maxconn,
            "used_connections": 0
        }

    # Get pool statistics
    min_conn = pool.minconn
    max_conn = pool.maxconn
    used_conn = len(pool._used)

    logger.info(f"Database connection pool status: {used_conn} used of {max_conn} max connections")

    # Check if pool is near capacity and should be reset
    if used_conn > max_conn * 0.8:
        logger.warning(
            f"Database connection pool is at {(used_conn / max_conn) * 100:.1f}% capacity, consider increasing max_connections")

    # Check for leaked connections (connections used for very long periods)
    if hasattr(pool, '_used') and pool._used:
        old_connections = []
        current_time = time.time()

        for conn_id, (conn, timestamp) in pool._used.items():
            # Check if connection has been held for more than 10 minutes
            if current_time - timestamp > 600:
                old_connections.append((conn_id, current_time - timestamp))

        if old_connections:
            logger.warning(f"Found {len(old_connections)} potentially leaked database connections")
            for conn_id, age in old_connections:
                logger.warning(f"Connection {conn_id} has been active for {age:.1f} seconds")

    return {
        "status": "checked",
        "min_connections": min_conn,
        "max_connections": max_conn,
        "used_connections": used_conn
    }
