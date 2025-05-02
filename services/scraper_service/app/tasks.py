# services/scraper_service/app/tasks.py

import logging
from datetime import datetime, timedelta, timezone

import boto3
import uuid

from redis import Redis
from contextlib import contextmanager

from common.db.session import db_session
from common.utils.unified_request_utils import fetch_ads_flatfy
from common.config import GEO_ID_MAPPING_FOR_INITIAL_RUN, AWS_CONFIG, REDIS_URL
from common.celery_app import celery_app
from common.utils.unified_request_utils import make_request
from common.utils.ad_utils import process_and_insert_ad
from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.repositories.ad_repository import AdRepository
from common.db.models import Ad
from sqlalchemy import func

# ---------------------------
# Configuration & Initialization
# ---------------------------

logger = logging.getLogger(__name__)

redis_client = Redis.from_url(REDIS_URL)


def acquire_lock(lock_name, expire_time=3600):
    """
    Acquire a Redis lock with the given name and expiration time.

    Args:
        lock_name: Name of the lock
        expire_time: Lock expiration time in seconds

    Returns:
        lock_id if lock acquired, None otherwise
    """
    lock_key = f"lock:{lock_name}"
    lock_id = str(uuid.uuid4())

    # Try to acquire the lock
    acquired = redis_client.set(lock_key, lock_id, ex=expire_time, nx=True)
    if acquired:
        logger.info(f"Acquired lock {lock_name} with ID {lock_id}")
        return lock_id
    return None


def release_lock(lock_name, lock_id):
    """
    Release a Redis lock if it is still held by us.

    Args:
        lock_name: Name of the lock
        lock_id: ID of the lock to release

    Returns:
        True if released, False otherwise
    """
    lock_key = f"lock:{lock_name}"

    # Use a Lua script to atomically check and delete the lock
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    else
        return 0
    end
    """
    result = redis_client.eval(script, 1, lock_key, lock_id)
    if result:
        logger.info(f"Released lock {lock_name} with ID {lock_id}")
        return True
    else:
        logger.warning(f"Failed to release lock {lock_name} - not owned by us or already expired")
        return False


@contextmanager
def redis_lock(lock_name, expire_time=3600):
    """
    Context manager for Redis locks.

    Args:
        lock_name: Name of the lock
        expire_time: Lock expiration time in seconds

    Yields:
        tuple: (acquired, lock_id) where acquired is True if lock was acquired
    """
    lock_key = f"lock:{lock_name}"
    lock_id = str(uuid.uuid4())

    # Try to acquire the lock
    acquired = redis_client.set(lock_key, lock_id, ex=expire_time, nx=True)
    if acquired:
        logger.info(f"Acquired lock {lock_name} with ID {lock_id}")
    else:
        logger.info(f"Failed to acquire lock {lock_name}")

    try:
        yield acquired, lock_id
    finally:
        # Release the lock if we acquired it
        if acquired:
            pipe = redis_client.pipeline()
            pipe.get(lock_key)
            pipe.delete(lock_key)
            key_val, _ = pipe.execute()

            if key_val and key_val.decode() != lock_id:
                logger.error(f"Lock {lock_key} was stolen!")
            else:
                logger.info(f"Released lock {lock_name} with ID {lock_id}")


# Initialize boto3 S3 client (using AWS_CONFIG from common/config.py)
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_CONFIG["access_key"],
    aws_secret_access_key=AWS_CONFIG["secret_key"],
    region_name=AWS_CONFIG["region"]
)


# ---------------------------
# Celery Tasks and Scraper Functions
# ---------------------------

@celery_app.task(name="scraper_service.app.tasks.fetch_new_ads")
def fetch_new_ads() -> None:
    try:
        with db_session() as db:
            # Get distinct cities from active users' filters using repository

            # Using repository methods for better abstraction
            active_cities = SubscriptionRepository.get_active_cities(db)

            if not active_cities:
                logger.info("No subscribed cities found.")
                return

            for city in active_cities:
                logger.info(f"Fetching new ads for city: {city}")
                _scrape_ads_for_city(city)
    except Exception as e:
        logger.error(f"Error fetching new ads: {e}")


def _scrape_ads_for_city(geo_id: int) -> None:
    """
    Scrapes ads for a given city (geo_id) and property type.
    """
    property_types = {'apartment': 2}  # Extend this mapping as needed.
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    for property_type, section_id in property_types.items():
        page = 1
        while True:
            ads = _scrape_ads_from_page(geo_id, section_id, page)
            if not ads:
                break

            found_new = False
            for ad in ads:
                inserted_id = _insert_ad_if_new(ad, geo_id, property_type, cutoff_time)
                if inserted_id:
                    found_new = True

            if not found_new:
                break
            page += 1


def _scrape_ads_from_page(geo_id: int, section_id: int, page: int) -> list:
    """
    Scrapes ads from a single page based on provided parameters.
    """
    base_url = "https://flatfy.ua/api/realties"
    params = {
        "currency": "UAH",
        "geo_id": geo_id,
        "group_collapse": 1,
        "has_eoselia": "false",
        "is_without_fee": "false",
        "lang": "uk",
        "page": page,
        "price_sqm_currency": "UAH",
        "section_id": section_id,
        "sort": "insert_time"
    }
    try:
        # Use the centralized make_request utility instead of the local one
        response = make_request(
            url=base_url,
            method='get',
            params=params,
            timeout=15,
            retries=5
        )

        if not response:
            return []

        data = response.json()
        return data.get("data", [])
    except Exception as e:
        logger.error(f"Failed to scrape page {page} for section_id {section_id} and geo_id {geo_id}: {e}")
        return []


def _insert_ad_if_new(ad_data: dict, geo_id: int, property_type: str, cutoff_time: datetime) -> int:
    # Replace with:
    with db_session() as db:
        # Get external ID
        ad_unique_id = str(ad_data.get("id", ""))
        if not ad_unique_id:
            return None

        # Check recency
        last_update_time_str = ad_data.get("download_time")
        if last_update_time_str:
            try:
                last_update_time = datetime.fromisoformat(last_update_time_str)
            except ValueError as e:
                logger.warning(f"Invalid date format in ad data: {last_update_time_str}, error: {e}")
                return None
            if last_update_time < cutoff_time:
                return None

        # Check if the ad already exists
        existing_ad = AdRepository.get_by_external_id(db, ad_unique_id)
        if existing_ad:
            return None

        # Insert new ad
        logger.info(f"Inserting new ad into DB: {ad_data.get('id')}")
        return process_and_insert_ad(ad_data, property_type, geo_id)


@celery_app.task(name="scraper_service.app.tasks.handle_new_records")
def handle_new_records(ad_ids: list) -> None:
    """Handler for newly inserted ad IDs."""
    logger.info(f"Handling newly inserted ad IDs: {ad_ids}")
    if not ad_ids:
        return

    try:
        with db_session() as db:

            new_ads = []
            for ad_id in ad_ids:
                ad = AdRepository.get_full_ad_data(db, ad_id)
                if ad:
                    new_ads.append(ad)

            if not new_ads:
                logger.info("No ads found for the provided IDs.")
                return

            # Dispatch to notifier service
            celery_app.send_task("notifier_service.app.tasks.sort_and_notify_new_ads", args=[new_ads])
            logger.info("Dispatched new ads to the Notifier for sorting and matching.")
    except Exception as e:
        logger.error(f"Error handling new records: {e}")


def is_initial_load_done() -> bool:
    """Checks if the initial ad load has been completed."""
    try:
        with db_session() as db:
            count = db.query(func.count(Ad.id)).scalar()
            return count > 0
    except Exception as e:
        logger.error(f"Error checking if initial load is done: {e}")
        return False  # Safer to return False if we can't determine


@celery_app.task(name="scraper_service.app.tasks.initial_30_day_scrape")
def initial_30_day_scrape() -> None:
    """Celery task for an initial 30-day scrape if no ads are loaded."""
    if is_initial_load_done():
        logger.info("Initial load is already done. Skipping.")
        return

    # Use the enhanced context manager
    with redis_lock("initial_scrape", expire_time=3600) as (acquired, _):
        if not acquired:
            logger.info("Initial scrape is already in progress by another worker. Skipping.")
            return

        # Your existing scrape code here
        for city_id, city_name in GEO_ID_MAPPING_FOR_INITIAL_RUN.items():
            logger.info(f">>> Starting initial 30-day scrape for {city_name} <<<")
            scrape_30_days_for_city(city_id)

        logger.info("Initial data load completed.")


def scrape_30_days_for_city(geo_id: int) -> None:
    """
    Scrapes ads for the past 30 days for a given city.
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=1)
    property_types = {'apartment': 2}  # Extend as needed.
    for property_type, section_id in property_types.items():
        page_number = 1
        ads_qty = 0
        while True:
            if ads_qty > 10:
                break
            data = fetch_ads_flatfy(geo_id=geo_id, page=page_number, section_id=section_id)
            if not data:
                break

            any_newer = False
            for ad in data:
                ad_time = parse_date(ad["insert_time"])
                if ad_time >= cutoff_date:
                    ads_qty += 1
                    insert_ad(ad, property_type, geo_id)
                    any_newer = True
                else:
                    any_newer = False
                    break

            if not any_newer:
                break
            page_number += 1


def parse_date(date_str: str) -> datetime:
    """
    Parses an ISO-format date string into a timezone-aware datetime object.
    """
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S+00:00").replace(tzinfo=timezone.utc)


def insert_ad(ad_data: dict, property_type: str, geo_id: int) -> int:
    """
    Inserts an ad into the database.
    """
    ad_unique_id = ad_data.get("id")
    if not ad_unique_id:
        return None

    # Use the unified ad insertion function
    logger.info("Inserting ad into DB...")
    return process_and_insert_ad(ad_data, property_type, geo_id)
