# services/notifier_service/app/tasks.py

from common.celery_app import celery_app
from common.db.models import find_users_for_ad
from common.db.database import execute_query
from common.utils.s3_utils import _upload_image_to_s3
from common.config import GEO_ID_MAPPING, get_key_by_value
import requests
import logging

# TELEGRAM_SEND_TASK = "telegram_service.app.tasks.send_message_task"
TELEGRAM_SEND_TASK = "telegram_service.app.tasks.send_ad_with_photos"

logger = logging.getLogger(__name__)


def get_ad_images(ad):
    ad_id = ad.get('id')
    sql_check = "SELECT * FROM ad_images WHERE ad_id = %s"
    rows = execute_query(sql_check, [ad_id], fetch=True)
    if rows:
        return [row["image_url"] for row in rows]


@celery_app.task(name="notifier_service.app.tasks.sort_and_notify_new_ads")
def sort_and_notify_new_ads(new_ads):
    """
    Receives a list of newly inserted ads from the scraper,
    checks which users want each ad, and sends them via
    Telegram or another channel.
    """
    logger.info("Received new ads for sorting/notification...")

    for ad in new_ads:
        s3_image_urls = get_ad_images(ad)
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
        f"📝 Опис: {ad.get('description')[:75]}...\n"
    )

    shared_app.send_task(
        # "telegram_service.app.tasks.send_message_task",
        "telegram_service.app.tasks.send_ad_with_photos",
        args=[user_id, text, s3_image_urls, ad.get('resource_url')]
    )


@celery_app.task(name="notifier_service.app.tasks.notify_user_with_ads")
def notify_user_with_ads(telegram_id, user_filters):
    """
    Scrapes ads based on user_filters and sends them to the user.
    """
    try:
        logger.info('Starting to notify user with ads...')
        base_url = 'https://flatfy.ua/api/realties'
        params = {
            'currency': 'UAH',
            'group_collapse': 1,
            'has_eoselia': 'false',
            'is_without_fee': 'false',
            'lang': 'uk',
            'page': 1,
            'price_max': str(int(user_filters.get('price_max')) * 40),
            'price_min': str(int(user_filters.get('price_min')) * 40),
            'price_sqm_currency': 'UAH',
            'section_id': 2,
            'sort': 'insert_time'
        }
        logger.info('Params: ' + str(params))
        room_counts = user_filters.get('rooms')
        if room_counts:
            # flatfy.ua поддерживает несколько параметров room_count
            # requests позволяет передавать список значений для одного ключа
            params['room_count'] = room_counts
        else:
            params.pop('room_count', None)

        city = user_filters.get('city')
        logger.info('City: ' + city)
        geo_id = get_key_by_value(city, GEO_ID_MAPPING)
        params['geo_id'] = geo_id

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
        }

        response = requests.get(base_url, params=params, headers=headers)
        if response.status_code != 200:
            logger.error(f"Не вдалося отримати оголошення: {response.status_code}")
            return
        data = response.json().get('data', [])
        logger.info('Received data.')
        for ad in data:
            ad_unique_id = ad.get("id")
            logger.info('Ad id is: ' + ad_unique_id)
            images = ad.get('images', [])
            logger.info('Images received.')
            uploaded_image_urls = []  # list of S3 URLs
            for image_info in images:
                image_id = image_info.get("image_id")
                if image_id:
                    original_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{image_id}.webp"
                    s3_url = _upload_image_to_s3(original_url, ad_unique_id)
                    if s3_url:
                        uploaded_image_urls.append(s3_url)
            logger.info('Uploaded images.')
            text = (
                f"💰 Ціна: {int(ad.get('price'))} грн.\n"
                f"🏙️ Місто: {city}\n"
                f"📍 Адреса: {ad.get('header')}\n"
                f"🛏️ Кіл-сть кімнат: {ad.get('room_count')}\n"
                f"📐 Площа: {ad.get('area_total')} кв.м.\n"
                f"🏢 Поверх: {ad.get('floor')} из {ad.get('floor_count')}\n"
                f"📝 Опис: {ad.get('text')[:75]}...\n"
            )
            resource_url = f"https://flatfy.ua/uk/redirect/{ad.get('id')}"

            celery_app.send_task(
                TELEGRAM_SEND_TASK,
                args=[telegram_id, text, uploaded_image_urls, resource_url]
            )

    except Exception as e:
        logger.error(f"Error notifying user with ads: {e}")
