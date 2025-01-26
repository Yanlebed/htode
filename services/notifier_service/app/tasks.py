# services/notifier_service/app/tasks.py

from common.celery_app import celery_app
from common.db.models import find_users_for_ad
from common.utils.logger import logger
import requests
from datetime import datetime, timezone, timedelta
import logging
import boto3

TELEGRAM_SEND_TASK = "telegram_service.app.tasks.send_message_task"

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


@celery_app.task(name="notifier_service.app.tasks.sort_and_notify_new_ads")
def sort_and_notify_new_ads(new_ads):
    """
    Receives a list of newly inserted ads from the scraper,
    checks which users want each ad, and sends them via
    Telegram or another channel.
    """
    logging.info("Received new ads for sorting/notification...")

    for ad in new_ads:
        s3_image_url = ad.get('image_url') # from DB
        users_to_notify = find_users_for_ad(ad)
        # `find_users_for_ad` is in your models.py and returns user_ids
        logging.info(f"Ad {ad['id']} -> Notifying users: {users_to_notify}")
        for user_id in users_to_notify:
            _notify_user_about_ad(user_id, ad, s3_image_url)


def _notify_user_about_ad(user_id, ad, s3_image_url):
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
        "telegram_service.app.tasks.send_message_task",
        args=[user_id, text, s3_image_url, ad.get('resource_url')]
    )


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


@celery_app.task(name="notifier_service.app.tasks.notify_user_with_ads")
def notify_user_with_ads(telegram_id, user_filters):
    """
    Scrapes ads based on user_filters and sends them to the user.
    """
    try:
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

        room_counts = user_filters.get('rooms')
        if room_counts:
            # flatfy.ua поддерживает несколько параметров room_count
            # requests позволяет передавать список значений для одного ключа
            params['room_count'] = room_counts
        else:
            params.pop('room_count', None)

        city = user_filters.get('city')
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
        geo_id = geo_id_mapping.get(city, 10009580)
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
        for ad in data:
            ad_unique_id = ad.get("id")
            image_url = None
            images = ad.get('images', [])
            if images:
                first_image_id = images[0].get('image_id')
                image_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{first_image_id}.webp"  # Проверьте правильность шаблона URL

            s3_image_url = None
            if image_url:
                s3_image_url = _upload_image_to_s3(image_url, ad_unique_id)

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
                args=[telegram_id, text, s3_image_url or image_url, resource_url]
            )

    except Exception as e:
        logger.error(f"Error notifying user with ads: {e}")
