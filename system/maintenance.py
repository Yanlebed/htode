# system/maintenance.py

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import or_, func

from common.celery_app import celery_app
from common.db.session import db_session
from common.db.models.favorite import FavoriteAd
from common.db.models.verification import VerificationCode
from common.db.models.user import User
from common.db.models.subscription import UserFilter
from common.db.repositories.ad_repository import AdRepository
from common.utils.s3_utils import delete_s3_image
from common.utils.cache import redis_client, CacheTTL
from common.config import GEO_ID_MAPPING

logger = logging.getLogger(__name__)


@celery_app.task(name='system.maintenance.check_expiring_subscriptions')
def check_expiring_subscriptions() -> Dict[str, Any]:
    """
    Check for expiring subscriptions and send reminders.
    """
    start_time = time.time()

    try:
        with db_session() as db:
            # Get users with subscriptions expiring in the next few days
            reminders_sent = 0

            # Check for subscriptions expiring in 3, 2, and 1 days
            for days in [3, 2, 1]:
                future_date = datetime.now() + timedelta(days=days, hours=1)
                past_date = datetime.now() + timedelta(days=days - 1)

                # Get users whose subscription expires in the specified time window
                users = db.query(User).filter(
                    User.subscription_until.isnot(None),
                    User.subscription_until > datetime.now(),
                    User.subscription_until < future_date,
                    User.subscription_until > past_date
                ).all()

                for user in users:
                    # Determine template based on days remaining
                    days_word = "день" if days == 1 else "дні" if days < 5 else "днів"
                    end_date = user.subscription_until.strftime("%d.%m.%Y")

                    # Build the appropriate template
                    if days == 1:
                        template = (
                            "⚠️ Ваша підписка закінчується завтра!\n\n"
                            "Дата закінчення: {end_date}\n\n"
                            "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                        )
                    else:
                        template = (
                            "⚠️ Нагадування про підписку\n\n"
                            "Ваша підписка закінчується через {days} "
                            "{days_word}.\n"
                            "Дата закінчення: {end_date}\n\n"
                            "Щоб продовжити користуватися сервісом, оновіть підписку."
                        )

                    # Send notification
                    from common.messaging.tasks import send_notification
                    send_notification.delay(
                        user_id=user.id,
                        template=template,
                        data={
                            "days": days,
                            "days_word": days_word,
                            "end_date": end_date
                        }
                    )
                    reminders_sent += 1

            # Also notify on the day of expiration
            today = datetime.now().date()
            users_today = db.query(User).filter(
                User.subscription_until.isnot(None),
                func.date(User.subscription_until) == today
            ).all()

            for user in users_today:
                end_date = user.subscription_until.strftime("%d.%m.%Y %H:%M")

                # Send notification
                from common.messaging.tasks import send_notification
                send_notification.delay(
                    user_id=user.id,
                    template=(
                        "⚠️ Ваша підписка закінчується сьогодні!\n\n"
                        "Час закінчення: {end_date}\n\n"
                        "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                    ),
                    data={"end_date": end_date}
                )
                reminders_sent += 1

        execution_time = time.time() - start_time
        logger.info(f"Checked expiring subscriptions in {execution_time:.2f} seconds")

        return {
            "status": "success",
            "reminders_sent": reminders_sent,
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
    deleted_count = 0
    images_deleted_count = 0

    try:
        with db_session() as db:
            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=days_old)

            # Get old ads
            old_ads = AdRepository.get_older_than(db, cutoff_date)

            for ad in old_ads:
                should_delete = True

                # Check if ad is still active if requested
                if check_activity:
                    from common.services.ad_service import AdService
                    if not AdService.is_ad_inactive(ad.resource_url):
                        should_delete = False

                if should_delete:
                    # Get ad images before deleting
                    images = AdRepository.get_ad_images(db, ad.id)

                    # Delete the ad and related data
                    if AdRepository.delete_with_related(db, ad.id):
                        deleted_count += 1

                        # Delete images from S3
                        for image_url in images:
                            if delete_s3_image(image_url):
                                images_deleted_count += 1

                        # Clear cache
                        clear_ad_cache(ad.id, ad.resource_url)

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


def clear_ad_cache(ad_id: int, resource_url: str = None):
    """
    Clear all cache entries related to a specific ad

    Args:
        ad_id: ID of the ad
        resource_url: Optional resource URL for additional cache keys
    """
    keys_to_delete = [
        f"full_ad:{ad_id}",
        f"ad_images:{ad_id}",
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
    try:
        with db_session() as db:
            # Cleanup verification codes
            verification_codes_deleted = db.query(VerificationCode).filter(
                VerificationCode.expires_at < datetime.now()
            ).delete()

            # Cleanup email verification tokens
            # Using raw SQL because the EmailVerificationToken model appears to be missing
            from sqlalchemy import text
            result = db.execute(
                text("DELETE FROM email_verification_tokens WHERE expires_at < CURRENT_TIMESTAMP")
            )
            email_tokens_deleted = result.rowcount

            db.commit()

            logger.info(
                f"Cleaned up {verification_codes_deleted} verification codes and {email_tokens_deleted} email tokens")

            return {
                "verification_codes_deleted": verification_codes_deleted,
                "email_tokens_deleted": email_tokens_deleted
            }
    except Exception as e:
        logger.error(f"Error cleaning up expired verification codes: {e}")
        return {
            "verification_codes_deleted": 0,
            "email_tokens_deleted": 0,
            "error": str(e)
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

        with db_session() as db:
            # For database operations like VACUUM, we need to use raw SQL
            # and manage the connection manually since these operations
            # can't run inside a transaction

            # Get the raw connection from the SQLAlchemy session
            connection = db.connection()

            # These operations need to run outside a transaction
            old_isolation_level = connection.connection.isolation_level
            connection.connection.set_isolation_level(0)  # AUTOCOMMIT mode

            try:
                # VACUUM ANALYZE on each table
                for table in tables:
                    logger.info(f"Running VACUUM ANALYZE on {table}")
                    db.execute(f"VACUUM ANALYZE {table}")
                    operations.append(f"VACUUM ANALYZE {table}")

                # Update table statistics
                for table in tables:
                    logger.info(f"Running ANALYZE on {table}")
                    db.execute(f"ANALYZE {table}")
                    operations.append(f"ANALYZE {table}")

                # Optimize indexes
                logger.info("Reindexing database")
                db.execute("REINDEX DATABASE current_database()")
                operations.append("REINDEX DATABASE")
            finally:
                # Restore previous isolation level
                connection.connection.set_isolation_level(old_isolation_level)

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
        with db_session() as db:
            # 1. Warm up cache for active cities
            active_cities = db.query(UserFilter.city).join(
                User, UserFilter.user_id == User.id
            ).filter(
                UserFilter.city.isnot(None),
                or_(User.subscription_until > datetime.now(), User.free_until > datetime.now())
            ).distinct().all()

            # Cache city data
            for city_row in active_cities:
                city_id = city_row[0]  # Extract the city ID from the row
                city_key = f"city:{city_id}"
                redis_client.set(city_key, {
                    "id": city_id,
                    "name": GEO_ID_MAPPING.get(city_id, "Unknown")
                }, ex=CacheTTL.LONG)  # City data rarely changes
                cached_items += 1

            # 2. Warm up cache for most viewed ads
            # This is a more complex query that might be easier with raw SQL
            # Here's the ORM equivalent:
            top_ads_subquery = db.query(
                FavoriteAd.ad_id,
                func.count(FavoriteAd.ad_id).label('view_count')
            ).group_by(
                FavoriteAd.ad_id
            ).order_by(
                func.count(FavoriteAd.ad_id).desc()
            ).limit(50).subquery()

            top_ads = db.query(top_ads_subquery.c.ad_id).all()

            if top_ads:
                ad_ids = [row[0] for row in top_ads]

                # Batch fetch ad data
                from common.db.operations import batch_get_full_ad_data
                batch_get_full_ad_data(ad_ids)
                cached_items += len(ad_ids)

            # 3. Warm up cache for active users
            active_users = db.query(User.id).filter(
                User.last_active > datetime.now() - timedelta(days=7)
            ).limit(100).all()

            if active_users:
                user_ids = [row[0] for row in active_users]

                # Batch fetch user filters
                from common.db.operations import batch_get_user_filters
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


@celery_app.task(name='system.maintenance.check_subscription_statistics')
def check_subscription_statistics() -> Dict[str, Any]:
    """
    Generate and save subscription statistics

    Returns:
        Dictionary with subscriber counts and statistics
    """
    start_time = time.time()

    try:
        with db_session() as db:
            # Count active subscribers
            active_subscribers = db.query(func.count(User.id)).filter(
                or_(
                    User.subscription_until > datetime.now(),
                    User.free_until > datetime.now()
                )
            ).scalar()

            # Count paid subscribers
            paid_subscribers = db.query(func.count(User.id)).filter(
                User.subscription_until > datetime.now()
            ).scalar()

            # Count free trial subscribers
            free_trial_subscribers = db.query(func.count(User.id)).filter(
                User.free_until > datetime.now(),
                or_(
                    User.subscription_until.is_(None),
                    User.subscription_until < datetime.now()
                )
            ).scalar()

            # Count subscribers by platform
            telegram_subscribers = db.query(func.count(User.id)).filter(
                User.telegram_id.isnot(None),
                or_(
                    User.subscription_until > datetime.now(),
                    User.free_until > datetime.now()
                )
            ).scalar()

            viber_subscribers = db.query(func.count(User.id)).filter(
                User.viber_id.isnot(None),
                or_(
                    User.subscription_until > datetime.now(),
                    User.free_until > datetime.now()
                )
            ).scalar()

            whatsapp_subscribers = db.query(func.count(User.id)).filter(
                User.whatsapp_id.isnot(None),
                or_(
                    User.subscription_until > datetime.now(),
                    User.free_until > datetime.now()
                )
            ).scalar()

            # Count by subscription filter
            subscription_counts = {}

            # Count by city
            city_counts = db.query(
                UserFilter.city,
                func.count(UserFilter.city).label('count')
            ).join(
                User, UserFilter.user_id == User.id
            ).filter(
                or_(
                    User.subscription_until > datetime.now(),
                    User.free_until > datetime.now()
                ),
                UserFilter.city.isnot(None)
            ).group_by(
                UserFilter.city
            ).all()

            city_stats = {
                GEO_ID_MAPPING.get(city_id, f"Unknown ({city_id})"): count
                for city_id, count in city_counts
            }

            subscription_counts["by_city"] = city_stats

            # Count by property type
            property_type_counts = db.query(
                UserFilter.property_type,
                func.count(UserFilter.property_type).label('count')
            ).join(
                User, UserFilter.user_id == User.id
            ).filter(
                or_(
                    User.subscription_until > datetime.now(),
                    User.free_until > datetime.now()
                ),
                UserFilter.property_type.isnot(None)
            ).group_by(
                UserFilter.property_type
            ).all()

            property_stats = {
                property_type: count for property_type, count in property_type_counts
            }

            subscription_counts["by_property_type"] = property_stats

            # Store statistics in Redis for later access
            statistics = {
                "timestamp": datetime.now().isoformat(),
                "active_subscribers": active_subscribers,
                "paid_subscribers": paid_subscribers,
                "free_trial_subscribers": free_trial_subscribers,
                "platform_breakdown": {
                    "telegram": telegram_subscribers,
                    "viber": viber_subscribers,
                    "whatsapp": whatsapp_subscribers
                },
                "subscription_counts": subscription_counts
            }

            redis_client.set("subscription_statistics", statistics, ex=86400)  # Cache for 1 day

            execution_time = time.time() - start_time

            return {
                "status": "success",
                "statistics": statistics,
                "execution_time_seconds": execution_time
            }
    except Exception as e:
        logger.error(f"Error generating subscription statistics: {e}")
        return {
            "status": "error",
            "error": str(e),
            "execution_time_seconds": time.time() - start_time
        }