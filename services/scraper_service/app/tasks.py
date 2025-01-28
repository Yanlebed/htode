# services/scraper_service/app/tasks.py

import boto3
import logging
import random
from time import sleep
import requests
from datetime import datetime, timedelta, timezone
from common.db.database import execute_query
from common.utils.s3_utils import _upload_image_to_s3

from common.celery_app import celery_app

# You might have some config with base URLs or any other relevant settings

logger = logging.getLogger(__name__)

S3_BUCKET = "htodebucket"  # os.getenv("AWS_S3_BUCKET", "your-bucket-name")
S3_PREFIX = "ads-images/"  # os.getenv("AWS_S3_BUCKET_PREFIX", "")
CLOUDFRONT_DOMAIN = "https://d3h86hbbdu2c7h.cloudfront.net"  # os.getenv("AWS_CLOUDFRONT_DOMAIN")  # if you have one
# DDOS protection

s3_client = boto3.client(
    's3',
    aws_access_key_id="AKIAS74TMCYOZMLDIA6K",  # os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key="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",  # os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name="eu-west-1"  # os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)

USER_AGENTS = [
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:100.0) Gecko/20100101 Firefox/100.0",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 ...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...",
]

PROXIES = [
    "http://proxy1.example:8080",
    "http://proxy2.example:8080",
]

# GEO_ID_MAPPING = {10000020: 'Львов', 10000060: 'Днепр', 10003908: 'Винница', 10007252: 'Житомир',
#                   10007846: 'Запорожье', 10008717: 'Ивано-Франковск', 10009570: 'Одесса', 10009580: 'Киев',
#                   10011240: 'Кропивницкий', 10012656: 'Луцк', 10013982: 'Николаев', 10018885: 'Полтава',
#                   10019894: 'Ровно', 10022820: 'Сумы', 10023304: 'Тернополь', 10023968: 'Ужгород',
#                   10024345: 'Харьков', 10024395: 'Херсон', 10024474: 'Хмельницкий'}
# GEO_ID_MAPPING = {10000020: 'Львів', 10009580: 'Київ'}
GEO_ID_MAPPING = {10000020: 'Львів'}


def get_random_user_agent():
    return random.choice(USER_AGENTS)


def get_random_proxy():
    return random.choice(PROXIES)


def make_request(url, params=None, max_retries=5, use_proxies=False, rotate_user_agents=True):
    """
    Make an HTTP GET request with optional retry logic, proxy rotation, user-agent rotation.
    Returns response object on success or raises an Exception if all attempts fail.
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
            # If you want to rotate proxies, pick one:
            proxy_dict = {}
            if use_proxies and PROXIES:
                chosen_proxy = get_random_proxy()
                proxy_dict = {
                    "http": chosen_proxy,
                    "https": chosen_proxy
                }

            logger.info(f"make_request attempt={attempt}, url={url}, params={params}, proxy={proxy_dict}")

            response = requests.get(url, params=params, headers=headers, proxies=proxy_dict, timeout=15)
            # Raise if not 200
            response.raise_for_status()
            return response  # success
        except Exception as e:
            logger.warning(f"Request attempt #{attempt} failed: {e}")
            if attempt < max_retries:
                sleep(2)  # short sleep before retry
            else:
                logger.error(f"All {max_retries} attempts failed for URL={url}")
                raise


@celery_app.task(name="scraper_service.app.tasks.fetch_new_ads")
def fetch_new_ads():
    # Query distinct subscribed cities (active subscriptions) from DB
    sql = """
    SELECT DISTINCT uf.city
    FROM user_filters uf
    JOIN users u ON uf.user_id = u.id
    WHERE uf.city IS NOT NULL
      AND (u.subscription_until > now() OR u.free_until > now())
    """
    rows = execute_query(sql, fetch=True)
    if not rows:
        return

    distinct_cities = [r["city"] for r in rows if r["city"]]
    for city in distinct_cities:
        geo_id = map_city_to_geo_id(city)
        _scrape_ads_for_city(geo_id)


def map_city_to_geo_id(city: str) -> int:
    # Example from your existing code
    geo_id_mapping = {
        'Київ': 10009580,
        'Харків': 10000050,
        'Одеса': 10009570,
        'Дніпро': 10000060,
        'Львів': 10000020,
        'Вінниця': 10003908,
        'Житомир': 10007252,
        'Запоріжжя': 10007846,
        'Івано-Франківськ': 10008717,
        'Кропивницький': 10011240,
        'Луцьк': 10012656,
        'Миколаїв': 10013982,
        'Полтава': 10018885,
        'Рівне': 10019894,
        'Суми': 10022820,
        'Тернопіль': 10023304,
        'Ужгород': 10023968,
        'Херсон': 10024395,
        'Хмельницький': 10024474,
    }
    return geo_id_mapping.get(city, 10009580)  # default to Kyiv or something


def _scrape_ads_for_city(geo_id: int):
    property_types = {'apartment': 2}#, 'house': 4}
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    for property_type, section_id in property_types.items():
        page = 1
        while True:
            ads = _scrape_ads_from_page(geo_id, section_id, page)
            if not ads:
                break

            found_new = False
            for ad in ads:
                # parse ad's time, see if it's older than cutoff, etc.
                # insert in DB if new
                inserted_id = _insert_ad_if_new(ad, geo_id, property_type, cutoff_time)
                if inserted_id:
                    found_new = True

            if not found_new:
                # if none were inserted or they're older than cutoff
                break
            page += 1


def _scrape_ads_from_page(geo_id, section_id, page):
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
        response = make_request(base_url, params=params, max_retries=5, use_proxies=False, rotate_user_agents=True)
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        logger.error(f"Failed to scrape page {page} for section_id {section_id} and geo_id {geo_id}: {e}")
        return []


def insert_ad_images(ad_id, image_urls):
    sql = "INSERT INTO ad_images (ad_id, image_url) VALUES (%s, %s)"
    for url in image_urls:
        execute_query(sql, (ad_id, url))


def _insert_ad_if_new(ad_data, geo_id, property_type, cutoff_time):
    """
    Inserts ad into DB if it doesn't exist yet (by unique URL or ad ID).
    Returns newly inserted ad_id or None if already existed or error.
    """

    ad_unique_id = str(ad_data.get("id", ""))  # or another unique field
    city = GEO_ID_MAPPING.get(geo_id)

    if not ad_unique_id:
        return None

    last_update_time_str = ad_data.get(
        "download_time")  # 2025-01-23T20:13:33+00:00 in the ad_data, and we should +2 hours local
    if last_update_time_str:
        last_update_time = datetime.fromisoformat(last_update_time_str)
        if last_update_time < cutoff_time:
            return None

    # Check if we already have this ad
    check_sql = "SELECT id FROM ads WHERE external_id = %s"
    params = [ad_unique_id]
    existing = execute_query(check_sql, params, fetchone=True)
    if existing:
        return None  # already have it

    # Optional: If the ad_data includes an image URL, upload it to S3
    images = ad_data.get('images', [])
    uploaded_image_urls = []  # list of S3 URLs
    for image_info in images:
        image_id = image_info.get("image_id")
        if image_id:
            original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
            s3_url = _upload_image_to_s3(original_url, ad_unique_id)
            if s3_url:
                uploaded_image_urls.append(s3_url)

    logger.info('Inserting ad into DB!!!')

    # Insert into DB, including the S3-based URL
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
        city,
        ad_data.get("header"),
        ad_data.get("price"),
        ad_data.get("area_total"),
        ad_data.get("room_count"),
        ad_data.get("floor"),
        ad_data.get("floor_count"),
        ad_data.get("insert_time"),
        ad_data.get("text"),
        ad_data.get("resource_url")
    ]

    row = execute_query(insert_sql, params, fetchone=True)
    insert_ad_images(ad_unique_id, uploaded_image_urls)
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


def is_initial_load_done():
    # Check if the ads table has at least one row
    sql = "SELECT COUNT(*) as cnt FROM ads"
    row = execute_query(sql, fetchone=True)
    count = row["cnt"]
    return count > 0


@celery_app.task(name="scraper_service.app.tasks.initial_30_day_scrape")
def initial_30_day_scrape():
    if is_initial_load_done():
        logger.info("Initial load is already done. Skipping.")
        return

    for city_id, city_name in GEO_ID_MAPPING.items():
        logger.info(">>> Starting initial 30-day scrape for " + city_name + " <<<")
        scrape_30_days_for_city(city_id)

    logger.info("Initial data load completed.")

    # Optionally, mark initial load as done in the DB
    # e.g., INSERT INTO meta_settings(key, value) VALUES ('initial_load_done', 'true');


def scrape_30_days_for_city(geo_id):
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=1)
    property_types = {'apartment': 2}#, 'house': 4}
    for property_type, section_id in property_types.items():
        page_number = 1
        while True:
            # 1) Do a request
            data = fetch_page(geo_id, section_id, page_number)
            if not data:
                break

            any_newer = False
            for ad in data:
                ad_time = parse_date(ad["insert_time"])  # 2025-01-26T10:13:14+00:00
                if ad_time >= cutoff_date:
                    # Insert or update DB
                    insert_ad(ad, property_type, geo_id)
                    any_newer = True
                else:
                    # This ad is older than 30 days
                    any_newer = False
                    break

            if not any_newer:
                break

            page_number += 1
            sleep(1)  # 1 request per second to avoid overloading the source


def fetch_page(geo_id, section_id, page_number):
    # Implement the logic to fetch a page of ads for a city
    # Return a list of ad dicts or []
    try:
        base_url = 'https://flatfy.ua/api/realties'
        params = {
            'geo_id': geo_id,
            'currency': 'UAH',
            'group_collapse': 1,
            'has_eoselia': 'false',
            'is_without_fee': 'false',
            'lang': 'uk',
            'page': page_number,
            'price_sqm_currency': 'UAH',
            'section_id': section_id,
            'sort': 'insert_time'
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
        }
        logger.info(f"Fetching page {page_number} for geo_id {geo_id} and section_id {section_id}...")
        response = requests.get(base_url, params=params, headers=headers)
        if response.status_code != 200:
            logger.error(f"Не вдалося отримати оголошення: {response.status_code}")
            return
        data = response.json().get('data', [])
        return data
    except Exception as e:
        logger.error(f"Failed to fetch page {page_number} for geo_id {geo_id}: {e}")
        return []


def parse_date(date_str):
    # Parse the date string into a datetime object
    # Example implementation:
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S+00:00").replace(tzinfo=timezone.utc)


def insert_ad(ad_data, property_type, geo_id):
    # Insert the ad into the ads table
    ad_unique_id = ad_data.get("id")
    city = GEO_ID_MAPPING.get(geo_id)
    resource_url = f"https://flatfy.ua/uk/redirect/{ad_unique_id}"
    images = ad_data.get('images', [])
    uploaded_image_urls = []  # list of S3 URLs
    for image_info in images:
        image_id = image_info.get("image_id")
        if image_id:
            original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
            s3_url = _upload_image_to_s3(original_url, ad_unique_id)
            if s3_url:
                uploaded_image_urls.append(s3_url)

    logger.info('Inserting ad into DB...')

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
    RETURNING id
        """
    params = [
        ad_unique_id,
        property_type,
        city,
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
    ad_id = row["id"]  # this is the internal ads.id
    insert_ad_images(ad_id, uploaded_image_urls)
    # insert_ad_images(ad_unique_id, uploaded_image_urls)
