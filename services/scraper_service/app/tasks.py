import os
import logging
import random
from time import sleep
from datetime import datetime, timedelta, timezone

import boto3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fake_useragent import UserAgent

from common.db.database import execute_query
from common.utils.s3_utils import _upload_image_to_s3
from common.utils.req_utils import fetch_ads_flatfy
from common.config import GEO_ID_MAPPING_FOR_INITIAL_RUN
from common.db.models import store_ad_phones
from common.celery_app import celery_app

# ---------------------------
# Configuration & Initialization
# ---------------------------

logger = logging.getLogger(__name__)

# AWS S3 and CloudFront configuration
S3_BUCKET = os.getenv("AWS_S3_BUCKET", "htodebucket")
S3_PREFIX = os.getenv("AWS_S3_BUCKET_PREFIX", "ads-images/")
CLOUDFRONT_DOMAIN = os.getenv("AWS_CLOUDFRONT_DOMAIN", "https://d3h86hbbdu2c7h.cloudfront.net")

# Initialize boto3 S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "AKIAS74TMCYOZMLDIA6K"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "Oj8AoxASxahA0x03t9rlCZo5i1eb8vVWbzKzVyan"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "eu-west-1")
)

# Set up fake user agent
try:
    ua = UserAgent()
except Exception as e:
    logger.error(f"Failed to initialize fake user agent: {e}")
    ua = None

# List of proxy servers (if needed)
PROXIES = [
    "http://proxy1.example:8080",
    "http://proxy2.example:8080",
]


# ---------------------------
# Helper Functions
# ---------------------------

def get_random_user_agent() -> str:
    """
    Returns a random user agent using fake_useragent library,
    falling back to a default if necessary.
    """
    if ua:
        try:
            return ua.random
        except Exception as e:
            logger.warning(f"Error getting random user agent: {e}")
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
           "(KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36"


def get_random_proxy() -> str:
    """
    Returns a random proxy from the list.
    """
    return random.choice(PROXIES)


def get_requests_session() -> requests.Session:
    """
    Creates and returns a requests Session with a retry strategy.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


REQUESTS_SESSION = get_requests_session()


def make_request(url: str, params: dict = None, max_retries: int = 5,
                 use_proxies: bool = False, rotate_user_agents: bool = True) -> requests.Response:
    """
    Makes an HTTP GET request with retry logic, proxy rotation, and user-agent rotation.
    Returns the response on success or raises an exception after all retries fail.
    """
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            headers = {
                "User-Agent": get_random_user_agent() if rotate_user_agents else "Mozilla/5.0",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br, zstd",
            }
            proxy_dict = {}
            if use_proxies and PROXIES:
                chosen_proxy = get_random_proxy()
                proxy_dict = {"http": chosen_proxy, "https": chosen_proxy}

            logger.info(f"make_request attempt={attempt}, url={url}, params={params}, proxies={proxy_dict}")
            response = REQUESTS_SESSION.get(url, params=params, headers=headers, proxies=proxy_dict, timeout=15)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request attempt #{attempt} failed for URL={url}: {e}")
            if attempt < max_retries:
                sleep(2 ** attempt)  # exponential backoff
            else:
                logger.error(f"All {max_retries} attempts failed for URL={url}")
                raise


# ---------------------------
# Celery Tasks and Scraper Functions
# ---------------------------

@celery_app.task(name="scraper_service.app.tasks.fetch_new_ads")
def fetch_new_ads() -> None:
    """
    Celery task to fetch new ads for distinct subscribed cities.
    """
    sql = """
    SELECT DISTINCT uf.city
    FROM user_filters uf
    JOIN users u ON uf.user_id = u.id
    WHERE uf.city IS NOT NULL
      AND (u.subscription_until > now() OR u.free_until > now())
    """
    rows = execute_query(sql, fetch=True)
    if not rows:
        logger.info("No subscribed cities found.")
        return

    distinct_cities = [r["city"] for r in rows if r["city"]]
    for city in distinct_cities:
        logger.info(f"Fetching new ads for city: {city}")
        _scrape_ads_for_city(city)


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
        response = make_request(base_url, params=params, max_retries=5,
                                use_proxies=False, rotate_user_agents=True)
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        logger.error(f"Failed to scrape page {page} for section_id {section_id} and geo_id {geo_id}: {e}")
        return []


def insert_ad_images(ad_id, image_urls: list) -> None:
    """
    Inserts ad images into the database.
    """
    sql = "INSERT INTO ad_images (ad_id, image_url) VALUES (%s, %s)"
    for url in image_urls:
        execute_query(sql, (ad_id, url))


def _insert_ad_if_new(ad_data: dict, geo_id: int, property_type: str, cutoff_time: datetime) -> int:
    """
    Inserts an ad into the DB if it is new (based on its unique external ID and timestamp).
    Returns the newly inserted ad's internal ID or None.
    """
    ad_unique_id = str(ad_data.get("id", ""))
    if not ad_unique_id:
        return None

    last_update_time_str = ad_data.get("download_time")
    if last_update_time_str:
        try:
            last_update_time = datetime.fromisoformat(last_update_time_str)
        except ValueError as e:
            logger.warning(f"Invalid date format in ad data: {last_update_time_str}, error: {e}")
            return None
        if last_update_time < cutoff_time:
            return None

    # Check if this ad already exists
    check_sql = "SELECT id FROM ads WHERE external_id = %s"
    existing = execute_query(check_sql, [ad_unique_id], fetchone=True)
    if existing:
        return None

    # Process images by uploading them to S3
    images = ad_data.get('images', [])
    uploaded_image_urls = []
    for image_info in images:
        image_id = image_info.get("image_id")
        if image_id:
            original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
            s3_url = _upload_image_to_s3(original_url, ad_unique_id)
            if s3_url:
                uploaded_image_urls.append(s3_url)

    logger.info(f"Inserting ad into DB: {ad_data}")
    resource_url = f"https://flatfy.ua/uk/redirect/{ad_data.get('id')}"
    insert_sql = """
    INSERT INTO ads (external_id, property_type, city, address, price, square_feet, rooms_count, floor, total_floors, insert_time, description, resource_url)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (external_id) DO UPDATE
      SET property_type = EXCLUDED.property_type,
          city = EXCLUDED.city,
          address = EXCLUDED.address,
          price = EXCLUDED.price,
          square_feet = EXCLUDED.square_feet,
          rooms_count = EXCLUDED.rooms_count,
          floor = EXCLUDED.floor,
          total_floors = EXCLUDED.total_floors,
          insert_time = EXCLUDED.insert_time,
          description = EXCLUDED.description,
          resource_url = EXCLUDED.resource_url
    RETURNING id;
    """
    params = [
        ad_unique_id,
        property_type,
        geo_id,
        ad_data.get("header"),
        ad_data.get("price"),
        ad_data.get("area_total"),
        ad_data.get("room_count"),
        ad_data.get("floor"),
        ad_data.get("floor_count"),
        ad_data.get("insert_time"),
        ad_data.get("text"),
        resource_url
    ]
    row = execute_query(insert_sql, params, fetchone=True)
    if row:
        ad_id = row["id"]
        store_ad_phones(resource_url, ad_id)
        insert_ad_images(ad_id, uploaded_image_urls)
        return ad_id
    return None


@celery_app.task(name="scraper_service.app.tasks.handle_new_records")
def handle_new_records(ad_ids: list) -> None:
    """
    Handler for newly inserted ad IDs.
    Dispatches these ads to the notifier service for further processing.
    """
    logger.info(f"Handling newly inserted ad IDs: {ad_ids}")
    if not ad_ids:
        return

    sql = "SELECT * FROM ads WHERE id = ANY(%s)"
    new_ads = execute_query(sql, [ad_ids], fetch=True)
    if not new_ads:
        logger.info("No ads found for the provided IDs.")
        return

    from common.celery_app import celery_app as shared_app
    shared_app.send_task("notifier_service.app.tasks.sort_and_notify_new_ads", args=[new_ads])
    logger.info("Dispatched new ads to the Notifier for sorting and matching.")


def is_initial_load_done() -> bool:
    """
    Checks if the initial ad load has been completed.
    """
    sql = "SELECT COUNT(*) as cnt FROM ads"
    row = execute_query(sql, fetchone=True)
    return row["cnt"] > 0


@celery_app.task(name="scraper_service.app.tasks.initial_30_day_scrape")
def initial_30_day_scrape() -> None:
    """
    Celery task for an initial 30-day scrape if no ads are loaded.
    """
    if is_initial_load_done():
        logger.info("Initial load is already done. Skipping.")
        return

    for city_id, city_name in GEO_ID_MAPPING_FOR_INITIAL_RUN.items():
        logger.info(f">>> Starting initial 30-day scrape for {city_name} <<<")
        scrape_30_days_for_city(city_id)

    logger.info("Initial data load completed.")
    # Optionally, mark initial load as done in the DB.


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

    resource_url = f"https://flatfy.ua/uk/redirect/{ad_unique_id}"
    images = ad_data.get('images', [])
    uploaded_image_urls = []
    for image_info in images:
        image_id = image_info.get("image_id")
        if image_id:
            original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
            s3_url = _upload_image_to_s3(original_url, ad_unique_id)
            if s3_url:
                uploaded_image_urls.append(s3_url)

    insert_sql = """
    INSERT INTO ads (external_id, property_type, city, address, price, square_feet, rooms_count, floor, total_floors, insert_time, description, resource_url)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (external_id) DO UPDATE
      SET property_type = EXCLUDED.property_type,
          city = EXCLUDED.city,
          address = EXCLUDED.address,
          price = EXCLUDED.price,
          square_feet = EXCLUDED.square_feet,
          rooms_count = EXCLUDED.rooms_count,
          floor = EXCLUDED.floor,
          total_floors = EXCLUDED.total_floors,
          insert_time = EXCLUDED.insert_time,
          description = EXCLUDED.description,
          resource_url = EXCLUDED.resource_url
    RETURNING id;
    """
    params = [
        ad_unique_id,
        property_type,
        geo_id,
        ad_data.get("header"),
        ad_data.get("price"),
        ad_data.get("area_total"),
        ad_data.get("room_count"),
        ad_data.get("floor"),
        ad_data.get("floor_count"),
        ad_data.get("insert_time"),
        ad_data.get("text"),
        resource_url
    ]
    logger.info("Inserting ad into DB...")
    logger.info(f"Params for ad insertion: {params}")
    row = execute_query(insert_sql, params, fetchone=True)
    if row:
        ad_id = row["id"]
        store_ad_phones(resource_url, ad_id)
        insert_ad_images(ad_id, uploaded_image_urls)
        return ad_id
    return None
