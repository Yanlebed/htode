# services/scraper_service/app/tasks.py

import boto3
import logging
import random
from time import sleep
import requests
from datetime import datetime, timedelta, timezone
from common.db.database import execute_query
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

GEO_ID_MAPPING = {10000020: 'Львов', 10000060: 'Днепр', 10003908: 'Винница', 10007252: 'Житомир',
                  10007846: 'Запорожье', 10008717: 'Ивано-Франковск', 10009570: 'Одесса', 10009580: 'Киев',
                  10011240: 'Кропивницкий', 10012656: 'Луцк', 10013982: 'Николаев', 10018885: 'Полтава',
                  10019894: 'Ровно', 10022820: 'Сумы', 10023304: 'Тернополь', 10023968: 'Ужгород',
                  10024345: 'Харьков', 10024395: 'Херсон', 10024474: 'Хмельницкий'}


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
        'Киев': 10009580,
        'Одесса': 10009570,
        'Днепр': 10000060,
        'Львов': 10000020,
        'Винница': 10003908,
        'Житомир': 10007252,
        'Запорожье': 10007846,
        'Ивано-Франковск': 10008717,
        'Кропивницкий': 10011240,
        'Луцк': 10012656,
        'Николаев': 10013982,
        'Полтава': 10018885,
        'Ровно': 10019894,
        'Сумы': 10022820,
        'Тернополь': 10023304,
        'Ужгород': 10023968,
        'Харьков': 10024345,
        'Херсон': 10024395,
        'Хмельницкий': 10024474,
    }
    return geo_id_mapping.get(city, 10009580)  # default to Kyiv or something


def _scrape_ads_for_city(geo_id: int):
    page = 1
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    while True:
        ads = _scrape_ads_from_page(geo_id, page)
        if not ads:
            break

        found_new = False
        for ad in ads:
            # parse ad's time, see if it's older than cutoff, etc.
            # insert in DB if new
            inserted_id = _insert_ad_if_new(ad, geo_id, cutoff_time)
            if inserted_id:
                found_new = True

        if not found_new:
            # if none were inserted or they're older than cutoff
            break
        page += 1


def _scrape_ads_from_page(geo_id, page):
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
        "section_id": 2,
        "sort": "insert_time"
    }
    try:
        response = make_request(base_url, params=params, max_retries=5, use_proxies=False, rotate_user_agents=True)
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        logging.error(f"Failed to scrape page {page} for geo_id {geo_id}: {e}")
        return []


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
        # E.g. "ads-images/<ad_id>_<image_id>.jpg"
        image_id = image_url.split("/")[-1].split('.')[0]
        file_extension = image_url.split(".")[-1][:4]  # naive approach, e.g. "jpg", "png", "webp"
        s3_key = f"{S3_PREFIX}{ad_unique_id}_{image_id}.{file_extension}"

        # 3) Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=image_data,
            ContentType="image/jpeg",  # or detect from file_extension
            # ACL='public-read'  # or your desired ACL/policy
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


def _insert_ad_if_new(ad_data, geo_id, cutoff_time):
    """
    Inserts ad into DB if it doesn't exist yet (by unique URL or ad ID).
    Returns newly inserted ad_id or None if already existed or error.
    """

    ad_unique_id = str(ad_data.get("id", ""))  # or another unique field
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
    image_url = None
    images = ad_data.get('images', [])
    if images:
        first_image_id = images[0].get('image_id')
        image_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{first_image_id}.webp"  # Проверьте правильность шаблона URL

    s3_image_url = None
    if image_url:
        s3_image_url = _upload_image_to_s3(image_url, ad_unique_id)

    # Insert into DB, including the S3-based URL
    insert_sql = """
    INSERT INTO ads (external_id, title, city, price, rooms_count, insert_time, image_url)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """
    params = [
        ad_unique_id,
        ad_data.get("title", "N/A"),
        GEO_ID_MAPPING.get(geo_id),
        ad_data.get("price"),
        ad_data.get("room_count"),
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
