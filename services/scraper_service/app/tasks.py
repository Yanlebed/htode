# services/scraper_service/app/tasks.py

import os
import boto3
import logging
import requests
from datetime import datetime, timedelta
from common.db.database import execute_query
from common.celery_app import celery_app  # or from .celery_app import celery_app

# You might have some config with base URLs or any other relevant settings

logger = logging.getLogger(__name__)


@celery_app.task(name="scraper_service.app.tasks.fetch_new_ads")
def fetch_new_ads():
    """
    Periodic task that scrapes new ads from a source (page by page) and stores them in the DB.
    Then triggers the handler for new ads.
    """
    logger.info("Starting fetch_new_ads task...")

    # 1) Determine how far back we should collect ads
    interval_minutes = int(os.getenv("SCRAPER_INTERVAL", 5))
    interval_delta = timedelta(minutes=interval_minutes)
    cutoff_time = datetime.utcnow() - interval_delta

    # 2) Start from page 1 and move forward until ads are older than the cutoff
    page = 1
    newly_inserted_ad_ids = []

    while True:
        logger.info(f"Scraping page {page}...")
        ads = _scrape_ads_from_page(page)
        if not ads:
            logger.info(f"No ads on page {page}. Stopping.")
            break

        # Flag to know if we should continue to next page
        continue_to_next_page = False

        # 3) Process each ad
        for ad in ads:
            ad_time = ad.get("insert_time")  # or parse from ad data
            # Convert string to datetime if needed:
            # ad_time = datetime.strptime(ad["insert_time"], "%Y-%m-%d %H:%M:%S")

            # If this ad is older than our cutoff_time, we can stop paging
            if ad_time < cutoff_time:
                logger.info("Found ad older than cutoff time. Stopping further pages.")
                continue_to_next_page = False
                break
            else:
                # This ad is new enough to consider inserting in DB
                inserted_id = _insert_ad_if_new(ad)
                if inserted_id:
                    newly_inserted_ad_ids.append(inserted_id)
                # We saw at least one valid ad, so let's attempt next ads
                continue_to_next_page = True

        if not continue_to_next_page:
            break
        page += 1

    logger.info(f"Total new ads inserted: {len(newly_inserted_ad_ids)}")

    if newly_inserted_ad_ids:
        # 4) Trigger the handler for newly inserted ads
        #    e.g. "sorter" or "notifier" – depends on your architecture
        handle_new_records.delay(newly_inserted_ad_ids)
    else:
        logger.info("No new ads found in this run.")

    logger.info("fetch_new_ads task completed.")


def _scrape_ads_from_page(page):
    """
    Example function that does the actual GET to fetch ads for a given page.
    Replace with your real scraping logic and structure.
    """
    base_url = "https://example.com/api/ads"
    params = {
        "page": page,
        "per_page": 30  # example
    }
    # Add headers, proxies, etc. as needed
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        # Suppose the data structure is data["results"]
        return data.get("results", [])
    except Exception as e:
        logger.error(f"Error while scraping page {page}: {e}")
        return []


s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)

S3_BUCKET = os.getenv("AWS_S3_BUCKET", "your-bucket-name")
S3_PREFIX = os.getenv("AWS_S3_BUCKET_PREFIX", "")
CLOUDFRONT_DOMAIN = os.getenv("AWS_CLOUDFRONT_DOMAIN")  # if you have one


def _upload_image_to_s3(image_url, ad_unique_id):
    """
    Downloads the image from `image_url` and uploads to S3.
    Returns the final S3 (or CloudFront) URL if successful, else None.
    """
    try:
        # 1) Download image
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        image_data = resp.content

        # 2) Create a unique key for S3
        # E.g. "ads-images/<ad_id>_<timestamp>.jpg"
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        file_extension = image_url.split(".")[-1][:4]  # naive approach, e.g. "jpg", "png", "webp"
        s3_key = f"{S3_PREFIX}{ad_unique_id}_{timestamp}.{file_extension}"

        # 3) Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=image_data,
            ContentType="image/jpeg",  # or detect from file_extension
            ACL='public-read'  # or your desired ACL/policy
        )

        # 4) Build final URL
        if CLOUDFRONT_DOMAIN:
            final_url = f"{CLOUDFRONT_DOMAIN}/{s3_key}"
        else:
            final_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"

        return final_url

    except Exception as e:
        logger.error(f"Failed to upload image to S3: {e}")
        return None


def _insert_ad_if_new(ad_data):
    """
    Inserts ad into DB if it doesn't exist yet (by unique URL or ad ID).
    Returns newly inserted ad_id or None if already existed or error.
    """
    ad_unique_id = ad_data.get("id")  # or another unique field
    if not ad_unique_id:
        return None

    # Check if we already have this ad
    check_sql = "SELECT id FROM ads WHERE external_id = %s"
    existing = execute_query(check_sql, [ad_unique_id], fetchone=True)
    if existing:
        return None  # already have it

    # Optional: If the ad_data includes an image URL, upload it to S3
    image_url = ad_data.get("image_url")
    s3_image_url = None
    if image_url:
        s3_image_url = _upload_image_to_s3(image_url, ad_unique_id)

    # Insert into DB, including the S3-based URL
    insert_sql = """
    INSERT INTO ads (external_id, title, city, price, rooms_count, insert_time, created_at, image_url)
    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
    RETURNING id
    """
    params = [
        ad_unique_id,
        ad_data.get("title"),
        ad_data.get("city"),
        ad_data.get("price"),
        ad_data.get("rooms_count"),
        ad_data.get("insert_time"),  # parse to datetime if needed
        s3_image_url
    ]
    row = execute_query(insert_sql, params, fetchone=True)
    return row["id"] if row else None


@celery_app.task(name="scraper_service.app.tasks.handle_new_records")
def handle_new_records(ad_ids):
    """
    Handler for newly inserted ads.
    This is where you pass the ads on to a 'sorter' or 'notifier' service
    that checks user filters and dispatches them to the interested users.
    """

    logger.info(f"Handling newly inserted ad IDs: {ad_ids}")
    if not ad_ids:
        return

    # 1) Fetch the ad records from DB
    sql = """
    SELECT *
    FROM ads
    WHERE id = ANY(%s)
    """
    new_ads = execute_query(sql, [ad_ids], fetch=True)
    if not new_ads:
        logger.info("No ads found for these IDs.")
        return

    # 2) Possibly send them to a "notifier_service" task that does the sorting:
    # e.g. "sort_and_notify_new_ads"
    #     (You would implement `sort_and_notify_new_ads` in the notifier_service.)
    from common.celery_app import celery_app as shared_app

    shared_app.send_task(
        "notifier_service.app.tasks.sort_and_notify_new_ads",
        args=[new_ads],
    )

    logger.info("Dispatched new ads to the Notifier for sorting & user matching.")
