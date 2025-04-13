# services/notifier_service/app/tasks.py

from common.celery_app import celery_app
from common.db.models import find_users_for_ad, store_ad_phones
from common.db.database import execute_query
from common.utils.s3_utils import _upload_image_to_s3
from common.utils.req_utils import fetch_ads_flatfy
from common.config import GEO_ID_MAPPING, get_key_by_value
from common.utils.ad_utils import process_and_insert_ad, get_ad_images as utils_get_ad_images
import logging

TELEGRAM_SEND_TASK = "telegram_service.app.tasks.send_ad_with_extra_buttons"
logger = logging.getLogger(__name__)

def get_ad_images_local(ad):
    """
    Get images for an ad (renamed to avoid recursion)
    """
    ad_id = ad.get('id')
    return utils_get_ad_images(ad_id)  # Call the imported function

def insert_ad(ad_data, property_type, geo_id):
    """Insert the ad into the ads table"""
    return process_and_insert_ad(ad_data, property_type, geo_id)

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
        s3_image_urls = get_ad_images_local(ad)[0] if get_ad_images_local(ad) else None
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
            ad_id = process_and_insert_ad(ad, property_type, geo_id)
            if not ad_id:
                logger.warning(f"Failed to insert ad {ad.get('id')}")
                continue

            # Get the first image for the ad
            ad_images = get_ad_images(ad_id)
            first_image = ad_images[0] if ad_images else None

            ad_external_id = str(ad.get("id"))
            resource_url = f"https://flatfy.ua/uk/redirect/{ad_external_id}"

            text = (
                f"💰 Ціна: {int(ad.get('price'))} грн.\n"
                f"🏙️ Місто: {city}\n"
                f"📍 Адреса: {ad.get('header')}\n"
                f"🛏️ Кіл-сть кімнат: {ad.get('room_count')}\n"
                f"📐 Площа: {ad.get('area_total')} кв.м.\n"
                f"🏢 Поверх: {ad.get('floor')} из {ad.get('floor_count')}\n"
            )

            celery_args = [telegram_id, text, first_image, resource_url, ad_id, ad_external_id]
            logger.info(f'services/notifier_service/app/tasks:notify_user_with_ads. celery args - {celery_args}')
            celery_app.send_task(
                TELEGRAM_SEND_TASK,
                args=celery_args
            )

    except Exception as e:
        logger.error(f"Error notifying user with ads: {e}")