# services/notifier_service/app/tasks.py

from common.celery_app import celery_app
from common.db.models import find_users_for_ad
from common.utils.logger import logger
import requests
import datetime
import logging

TELEGRAM_SEND_TASK = "telegram_service.app.tasks.send_message_task"


@celery_app.task(name="notifier_service.app.tasks.sort_and_notify_new_ads")
def sort_and_notify_new_ads(new_ads):
    """
    Receives a list of newly inserted ads from the scraper,
    checks which users want each ad, and sends them via
    Telegram or another channel.
    """
    logging.info("Received new ads for sorting/notification...")

    for ad in new_ads:
        s3_image_url = ad.get('image_url')
        users_to_notify = find_users_for_ad(ad)
        # `find_users_for_ad` is in your models.py and returns user_ids
        logging.info(f"Ad {ad['id']} -> Notifying users: {users_to_notify}")
        for user_id in users_to_notify:
            _notify_user_about_ad(user_id, ad, s3_image_url)


def _notify_user_about_ad(user_id, ad, s3_image_url):
    from common.celery_app import celery_app as shared_app
    message_text = (
        f"Новое объявление!\n"
        f"Заголовок: {ad.get('title')}\n"
        # ...
    )
    shared_app.send_task(
        "telegram_service.app.tasks.send_message_task",
        args=[user_id, message_text, s3_image_url, ad.get('external_url')]
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
        users_to_notify = find_users_for_ad(ad)
        # `find_users_for_ad` is in your models.py and returns user_ids
        logging.info(f"Ad {ad['id']} -> Notifying users: {users_to_notify}")
        for user_id in users_to_notify:
            _notify_user_about_ad(user_id, ad)


def _notify_user_about_ad(user_id, ad):
    """
    Actual logic to create a message and enqueue a Celery task
    for telegram sending or direct call if you prefer.
    """
    from common.celery_app import celery_app as shared_app
    message_text = (
        f"Новое объявление!\n"
        f"Заголовок: {ad.get('title')}\n"
        f"Цена: {ad.get('price')}\n"
        # ...
    )
    # Here we assume you have a Telegram send task:
    shared_app.send_task(
        "telegram_service.app.tasks.send_message_task",
        args=[user_id, message_text]
    )


@celery_app.task(name="notifier_service.app.tasks.notify_user_with_ads")
def notify_user_with_ads(telegram_id, user_filters):
    """
    Scrapes ads based on user_filters and sends them to the user.
    """
    try:
        logging.info(f"Notifying user with ads: {telegram_id}")
        # Конструирование URL на основе фильтров пользователя
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
            'sort': 'relevance'
        }
        logging.info(f"User filters: {user_filters}")
        # Обработка 'room_count' как списка
        room_counts = user_filters.get('rooms')
        if room_counts:
            # flatfy.ua поддерживает несколько параметров room_count
            # requests позволяет передавать список значений для одного ключа
            params['room_count'] = room_counts
        else:
            params.pop('room_count', None)

        logging.info(f"Params: {params}")
        # Обработка 'insert_date_min' на основе 'listing_date'
        listing_date = user_filters.get('listing_date')
        if listing_date == 'today':
            insert_date_min = datetime.datetime.now().strftime('%Y-%m-%d')
        elif listing_date == '3_days' or listing_date == 'days':  # Добавили 'days'
            insert_date_min = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime('%Y-%m-%d')
        elif listing_date == 'week':
            insert_date_min = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        elif listing_date == 'month':
            insert_date_min = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        elif listing_date == 'all_time':
            insert_date_min = '1970-01-01'
        else:
            insert_date_min = '1970-01-01'
        params['insert_date_min'] = insert_date_min

        logging.info(f"Params after processing: {params}")

        # Маппинг 'city' на 'geo_id'
        city = user_filters.get('city')
        geo_id_mapping = {
            'Киев': 10009580,
            'Харьков': 10000050,
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
            # Добавьте другие города и их geo_id
        }
        geo_id = geo_id_mapping.get(city, 10009580)  # По умолчанию Киев
        params['geo_id'] = geo_id

        logging.info(f"Params after processing geo: {params}")

        # Выполнение GET-запроса
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
        }
        logging.info(f"Headers: {headers}")
        logging.info(f"Base URL: {base_url}")
        logging.info("Sending request...")

        response = requests.get(base_url, params=params, headers=headers)
        if response.status_code != 200:
            logger.error(f"Не удалось получить объявления: {response.status_code}")
            return
        logging.info("Request sent successfully.")
        data = response.json().get('data', [])[:2]
        for ad in data:
            # Извлечение URL изображения
            image_url = None
            images = ad.get('images', [])
            logging.info('Images are ready. Extracting image URL...')
            if images:
                first_image_id = images[0].get('image_id')
                image_url = f"https://market-images.lunstatic.net/lun-ua/720/720/images/{first_image_id}.webp"  # Проверьте правильность шаблона URL

            text = (
                f"📍 *{ad.get('title')}*\n"
                f"💰 Цена: {ad.get('price')} UAH\n"
                f"🏙️ Город: {ad.get('city')}\n"
                f"📍 Адрес: {ad.get('geo')}\n"
                f"🛏️ Комнат: {ad.get('room_count')}\n"
                f"📐 Площадь: {ad.get('area_total')} кв.м.\n"
                f"🏢 Этаж: {ad.get('floor')} из {ad.get('floor_count')}\n"
                f"📝 Описание: {ad.get('text')[:100]}...\n"
            )
            logging.info('Text is ready.')
            resource_url = f"https://flatfy.ua/uk/redirect/{ad.get('id')}"
            logging.info(f"Text: {text}")
            logging.info(f"Image URL: {image_url}")
            logging.info(f"Resource URL: {resource_url}")

            # Отправляем задачу на отправку сообщения пользователю
            celery_app.send_task(
                TELEGRAM_SEND_TASK,
                args=[telegram_id, text, image_url, resource_url]
            )

    except Exception as e:
        logger.error(f"Error notifying user with ads: {e}")
