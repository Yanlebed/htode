# services/notifier_service/app/tasks.py

from common.celery_app import celery_app
from common.db.models import find_users_for_ad, store_ad_phones
from common.db.database import execute_query
from common.utils.s3_utils import _upload_image_to_s3
from common.utils.req_utils import fetch_ads_flatfy
from common.config import GEO_ID_MAPPING, get_key_by_value
import logging

TELEGRAM_SEND_TASK = "telegram_service.app.tasks.send_ad_with_extra_buttons"
logger = logging.getLogger(__name__)


def get_ad_images(ad):
    ad_id = ad.get('id')
    sql_check = "SELECT * FROM ad_images WHERE ad_id = %s"
    rows = execute_query(sql_check, [ad_id], fetch=True)
    if rows:
        return [row["image_url"] for row in rows]


def insert_ad_images(ad_id, image_urls):
    sql = "INSERT INTO ad_images (ad_id, image_url) VALUES (%s, %s)"
    for url in image_urls:
        execute_query(sql, (ad_id, url))


def insert_ad(ad_data, property_type, geo_id):
    # Insert the ad into the ads table
    ad_unique_id = ad_data.get("id")
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
    logger.info('services/scraper_service/app/tasks:insert_ad: Inserting ad into DB...')
    logger.info(f'services/scraper_service/app/tasks:insert_ad: Params of ad to insert {params}')
    row = execute_query(insert_sql, params, fetchone=True)
    ad_id = row["id"]  # this is the internal ads.id
    store_ad_phones(resource_url, ad_id)
    insert_ad_images(ad_id, uploaded_image_urls)
    # insert_ad_images(ad_unique_id, uploaded_image_urls)
    return ad_id

@celery_app.task(name="notifier_service.app.tasks.sort_and_notify_new_ads")
def sort_and_notify_new_ads(new_ads):
    """
    Receives a list of newly inserted ads from the scraper,
    checks which users want each ad, and sends them via
    Telegram or another channel.
    """
    logger.info("Received new ads for sorting/notification...")
    logger.info(f'New ads {new_ads}')
    for ad in new_ads:
        s3_image_urls = get_ad_images(ad)[0]
        users_to_notify = find_users_for_ad(ad)
        # `find_users_for_ad` is in your models.py and returns user_ids
        logger.info(f"Ad {ad['id']} -> Notifying users: {users_to_notify}")
        for user_id in users_to_notify:
            _notify_user_about_ad(user_id, ad, s3_image_urls)


def _notify_user_about_ad(user_id, ad, s3_image_urls):
    from common.celery_app import celery_app as shared_app
    text = (
        f"💰 Ціна: {int(ad.get('price'))} грн.\n"
        f"🏙️ Місто: {ad.get('city')}\n"
        f"📍 Адреса: {ad.get('address')}\n"
        f"🛏️ Кіл-сть кімнат: {ad.get('rooms_count')}\n"
        f"📐 Площа: {ad.get('square_feet')} кв.м.\n"
        f"🏢 Поверх: {ad.get('floor')} из {ad.get('total_floors')}\n"
    )
    logger.info(f'FROM _notify_user_about_ad: external ad id {ad.get("external_id")}')
    shared_app.send_task(
        "telegram_service.app.tasks.send_ad_with_extra_buttons",
        args=[user_id, text, s3_image_urls, ad.get('resource_url'), ad.get("external_id")]
    )


@celery_app.task(name="notifier_service.app.tasks.notify_user_with_ads")
def notify_user_with_ads(telegram_id, user_filters):
    try:
        logger.info('Starting to notify user with ads...')
        city = user_filters.get('city')
        property_type = 2
        geo_id = get_key_by_value(city, GEO_ID_MAPPING)

        # Build optional params
        room_counts = user_filters.get('rooms')  # e.g. [1,2] or None
        price_min = user_filters.get('price_min')
        price_max = user_filters.get('price_max')
        # section_id=2 for apartment, or do dynamic

        data = fetch_ads_flatfy(
            geo_id=geo_id,
            page=1,
            room_count=room_counts,
            price_min=price_min,
            price_max=price_max,
            section_id=property_type
        )
        if not data:
            logger.info("No ads found with these filters.")
            return

        logger.info('Received data from fetch_ads_flatfy.')
        for ad in data:
            # handle each ad similarly
            ad_external_id = str(ad.get("id"))
            images = ad.get("images", [])
            uploaded_image_urls = []  # list of S3 URLs
            for image_info in images:
                image_id = image_info.get("image_id")
                if image_id:
                    original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
                    s3_url = _upload_image_to_s3(original_url, ad_external_id)
                    if s3_url:
                        uploaded_image_urls.append(s3_url)
            text = (
                f"💰 Ціна: {int(ad.get('price'))} грн.\n"
                f"🏙️ Місто: {city}\n"
                f"📍 Адреса: {ad.get('header')}\n"
                f"🛏️ Кіл-сть кімнат: {ad.get('room_count')}\n"
                f"📐 Площа: {ad.get('area_total')} кв.м.\n"
                f"🏢 Поверх: {ad.get('floor')} из {ad.get('floor_count')}\n"
            )
            resource_url = f"https://flatfy.ua/uk/redirect/{ad_external_id}"

            ad_id = insert_ad(ad, property_type, geo_id)

            celery_args = [telegram_id, text, uploaded_image_urls[0], resource_url, ad_id, ad_external_id]
            logger.info(f'services/notifier_service/app/tasks:notify_user_with_ads. celery args - {celery_args}')
            celery_app.send_task(
                TELEGRAM_SEND_TASK,
                args=celery_args
                # TODO: not sure if ad_unique_id is relevant  and maybe we need from DB
            )

    except Exception as e:
        logger.error(f"Error notifying user with ads: {e}")
