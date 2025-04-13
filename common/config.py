# common/config.py

import os

# Можно читать ENV или .env
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "myuser")
DB_PASS = os.getenv("DB_PASS", "mypass")
DB_NAME = os.getenv("DB_NAME", "mydb")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

GEO_ID_MAPPING = {
    10012684: 'Львів',
    10006463: 'Дніпро',
    10003908: 'Вінниця',
    10007252: 'Житомир',
    10007846: 'Запоріжжя',
    10008717: 'Івано-Франківськ',
    10016589: 'Одеса',
    10009580: 'Київ',
    514141: 'Київ (передмістя)',
    10011240: 'Кропивницький',
    10012656: 'Луцьк',
    10013982: 'Миколаїв',
    10018885: 'Полтава',
    10019894: 'Рівне',
    10022820: 'Суми',
    10023304: 'Тернопіль',
    10023968: 'Ужгород',
    10024345: 'Харків',
    10024395: 'Херсон',
    10024474: 'Хмельницький',
    10025145: 'Черкаси',
    10025207: 'Чернівці',
    10025209: 'Чернігів'
}
GEO_ID_MAPPING_FOR_INITIAL_RUN = {10012684: 'Львів'}


def get_key_by_value(value, geo_id_mapping):
    return next((k for k, v in geo_id_mapping.items() if v == value), None)


def build_ad_text(ad_row):
    # For example:
    city_name = GEO_ID_MAPPING.get(ad_row.get('city'))
    text = (
        f"💰 Ціна: {int(ad_row.get('price'))} грн.\n"
        f"🏙️ Місто: {city_name}\n"
        f"📍 Адреса: {ad_row.get('address')}\n"
        f"🛏️ Кіл-сть кімнат: {ad_row.get('rooms_count')}\n"
        f"📐 Площа: {ad_row.get('square_feet')} кв.м.\n"
        f"🏢 Поверх: {ad_row.get('floor')} из {ad_row.get('total_floors')}\n"
    )
    return text