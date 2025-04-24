# system/maintenance.py

import logging
import time
from datetime import datetime, timedelta
import requests
from typing import List, Tuple, Optional, Dict, Any

from common.celery_app import celery_app
from common.db.database import execute_query
from common.utils.s3_utils import delete_s3_image
from common.utils.request_utils import make_request

logger = logging.getLogger(__name__)


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

    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days_old)
    logger.info(f"Cutoff date for old ads: {cutoff_date}")

    # Get candidate ads for cleanup
    candidates = get_old_ads_for_cleanup(cutoff_date)
    logger.info(f"Found {len(candidates)} ads older than {days_old} days")

    if not candidates:
        return {
            "status": "completed",
            "ads_checked": 0,
            "ads_deleted": 0,
            "images_deleted": 0,
            "execution_time_seconds": time.time() - start_time
        }

    # Process ads in batches to avoid memory issues with large datasets
    batch_size = 100
    total_deleted = 0
    total_images_deleted = 0
    total_checked = 0

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        logger.info(
            f"Processing batch {i // batch_size + 1}/{(len(candidates) + batch_size - 1) // batch_size} ({len(batch)} ads)")

        # Process each ad in the batch
        deleted, images_deleted, checked = process_ads_batch(batch, check_activity)

        total_deleted += deleted
        total_images_deleted += images_deleted
        total_checked += checked

    execution_time = time.time() - start_time
    logger.info(
        f"Cleanup completed in {execution_time:.2f} seconds. Checked: {total_checked}, Deleted: {total_deleted}, Images deleted: {total_images_deleted}")

    return {
        "status": "completed",
        "ads_checked": total_checked,
        "ads_deleted": total_deleted,
        "images_deleted": total_images_deleted,
        "execution_time_seconds": execution_time
    }


def get_old_ads_for_cleanup(cutoff_date: datetime) -> List[Dict[str, Any]]:
    """
    Retrieve ads older than the cutoff date for potential cleanup.

    Args:
        cutoff_date: Date before which ads are considered old

    Returns:
        List of ad dictionaries with id, external_id, resource_url
    """
    sql = """
          SELECT id, external_id, resource_url
          FROM ads
          WHERE insert_time < %s \
          """

    return execute_query(sql, [cutoff_date], fetch=True) or []


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
    Delete an ad and all its related data (images, phones, favorites).

    Args:
        ad_id: ID of the ad to delete

    Returns:
        True if the ad was deleted successfully, False otherwise
    """
    try:
        # Start with related tables to maintain referential integrity
        # No need to delete from ad_images and ad_phones separately due to CASCADE

        # Delete from favorite_ads
        execute_query("DELETE FROM favorite_ads WHERE ad_id = %s", [ad_id])

        # Finally delete the ad itself
        execute_query("DELETE FROM ads WHERE id = %s", [ad_id])

        logger.info(f"Successfully deleted ad {ad_id} and related data")
        return True
    except Exception as e:
        logger.error(f"Error deleting ad {ad_id}: {e}")
        return False


@celery_app.task(name='system.maintenance.check_subscription_statistics')
def check_subscription_statistics() -> Dict[str, Any]:
    """
    Generate statistics about user subscriptions.

    Returns:
        Dictionary with subscription statistics
    """
    stats = {}

    # Total users
    total_users_query = "SELECT COUNT(*) as count FROM users"
    total_users_result = execute_query(total_users_query, fetchone=True)
    stats['total_users'] = total_users_result['count'] if total_users_result else 0

    # Active subscribers (paid or free)
    active_users_query = """
                         SELECT COUNT(*) as count \
                         FROM users
                         WHERE subscription_until > NOW() OR free_until > NOW() \
                         """
    active_users_result = execute_query(active_users_query, fetchone=True)
    stats['active_subscribers'] = active_users_result['count'] if active_users_result else 0

    # Paid subscribers
    paid_users_query = "SELECT COUNT(*) as count FROM users WHERE subscription_until > NOW()"
    paid_users_result = execute_query(paid_users_query, fetchone=True)
    stats['paid_subscribers'] = paid_users_result['count'] if paid_users_result else 0

    # Free trial users
    free_users_query = """
                       SELECT COUNT(*) as count \
                       FROM users
                       WHERE free_until > NOW() AND (subscription_until IS NULL OR subscription_until < NOW()) \
                       """
    free_users_result = execute_query(free_users_query, fetchone=True)
    stats['free_trial_users'] = free_users_result['count'] if free_users_result else 0

    # Users by messenger type
    messenger_stats_query = """
                            SELECT COUNT(CASE WHEN telegram_id IS NOT NULL THEN 1 END) as telegram_users, \
                                   COUNT(CASE WHEN viber_id IS NOT NULL THEN 1 END)    as viber_users, \
                                   COUNT(CASE WHEN whatsapp_id IS NOT NULL THEN 1 END) as whatsapp_users
                            FROM users \
                            """
    messenger_stats = execute_query(messenger_stats_query, fetchone=True)
    if messenger_stats:
        stats['telegram_users'] = messenger_stats['telegram_users']
        stats['viber_users'] = messenger_stats['viber_users']
        stats['whatsapp_users'] = messenger_stats['whatsapp_users']

    # Active subscriptions by city
    city_stats_query = """
                       SELECT uf.city, COUNT(DISTINCT uf.user_id) as user_count
                       FROM user_filters uf
                                JOIN users u ON uf.user_id = u.id
                       WHERE (u.subscription_until > NOW() OR u.free_until > NOW())
                         AND uf.city IS NOT NULL
                       GROUP BY uf.city
                       ORDER BY user_count DESC \
                       """
    city_stats = execute_query(city_stats_query, fetch=True) or []
    stats['subscriptions_by_city'] = city_stats

    logger.info(f"Generated subscription statistics: {stats}")
    return stats


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
