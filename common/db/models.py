# common/db/models.py
import time

from .database import execute_query
import datetime
import logging
from common.config import GEO_ID_MAPPING, get_key_by_value
from common.utils.phone_parser import extract_phone_numbers_from_resource

logger = logging.getLogger(__name__)


def get_or_create_user(telegram_id):
    logger.info(f"Getting user with telegram id: {telegram_id}")
    sql_check = "SELECT id FROM users WHERE telegram_id = %s"
    row = execute_query(sql_check, [telegram_id], fetchone=True)
    if row:
        logger.info(f"Found user with telegram id: {telegram_id}, user_id: {row['id']}")
        return row['id']

    logger.info(f"Creating user with telegram id: {telegram_id}")
    free_until = (datetime.datetime.now() + datetime.timedelta(days=7)).isoformat()
    sql_insert = """
                 INSERT INTO users (telegram_id, free_until)
                 VALUES (%s, %s) RETURNING id \
                 """
    user = execute_query(sql_insert, [telegram_id, free_until], fetchone=True, commit=True)  # Ensure commit=True
    if not user:
        logger.error(f"Failed to create user with telegram id: {telegram_id}")
        return None

    logger.info(f"Created user with telegram id: {telegram_id}, new user_id: {user['id']}")
    return user['id']


def update_user_filter(user_id, filters):
    logger.info(f"Updating filters for user_id: {user_id}")

    # First verify user exists
    check_sql = "SELECT id FROM users WHERE id = %s"
    user_exists = execute_query(check_sql, [user_id], fetchone=True)
    if not user_exists:
        logger.error(f"Cannot update filters - user_id {user_id} does not exist in database")
        raise ValueError(f"User ID {user_id} does not exist")

    property_type = filters.get('property_type')
    city = filters.get('city')
    geo_id = get_key_by_value(city, GEO_ID_MAPPING)
    rooms_count = filters.get('rooms')  # List or None
    price_min = filters.get('price_min')
    price_max = filters.get('price_max')

    sql_upsert = """
                 INSERT INTO user_filters (user_id, property_type, city, rooms_count, price_min, price_max)
                 VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (user_id)
    DO
                 UPDATE SET
                     property_type = EXCLUDED.property_type,
                     city = EXCLUDED.city,
                     rooms_count = EXCLUDED.rooms_count,
                     price_min = EXCLUDED.price_min,
                     price_max = EXCLUDED.price_max \
                 """
    logger.info(
        f"Executing query with params: [{user_id}, {property_type}, {geo_id}, {rooms_count}, {price_min}, {price_max}]")
    execute_query(sql_upsert, [user_id, property_type, geo_id, rooms_count, price_min, price_max], commit=True)


def start_free_subscription_of_user(user_id):
    logger.info('Starting free subscription for user %s', user_id)
    sql = "UPDATE users SET free_until = NOW() + interval '7 days' WHERE id = %s"
    execute_query(sql, [user_id])
    time.sleep(2)
    logger.info('Checking if subscription is active for user %s', user_id)
    select_sql = "SELECT * FROM users WHERE id = %s"
    rows = execute_query(select_sql, [user_id], fetch=True)
    if rows:
        row = rows[0]
        logger.info('Free subscription for user %s: %s', user_id, row)
    else:
        logger.info('Free subscription for user %s: None', user_id)
        select_all_sql = 'SELECT * FROM users'
        rows = execute_query(select_all_sql, fetch=True)
        logger.info('All users: %s', rows)


def get_user_filters(user_id):
    sql = "SELECT * FROM user_filters WHERE user_id = %s"
    rows = execute_query(sql, [user_id], fetch=True)
    return rows[0] if rows else None


def find_users_for_ad(ad):
    # TODO: If is_paused = TRUE, you skip it when searching for active subscriptions (like in find_users_for_ad, or wherever you want to ignore paused ones).
    """
    Возвращает список user_id, которым подходит объявление.
    """
    logger.info('Looking for users for ad: %s', ad)
    sql = """
          SELECT u.id AS user_id, uf.property_type, uf.city, uf.rooms_count, uf.price_min, uf.price_max
          FROM user_filters uf
                   JOIN users u ON uf.user_id = u.id
          WHERE (u.free_until > NOW() OR (u.subscription_until > NOW()))
            AND (uf.property_type = %s OR uf.property_type IS NULL)
            AND (uf.city = %s OR uf.city IS NULL)
            AND (uf.rooms_count = %s OR uf.rooms_count IS NULL)
            AND (uf.price_min IS NULL OR ad.price >= uf.price_min)
            AND (uf.price_max IS NULL OR ad.price <= uf.price_max) \
          """
    # Предполагается, что в `ads` есть соответствующие поля
    # Выполните SQL-запрос с передачей параметров объявления
    # Пример:
    ad_property_type = ad.get('property_type')
    ad_city = ad.get('city')
    ad_rooms = ad.get('rooms_count')
    ad_price = ad.get('price')
    ad_insert_time = ad.get('insert_time')

    # Выполняем SQL-запрос
    rows = execute_query(sql, [ad_property_type, ad_city, ad_rooms, ad_price, ad_price, ad_insert_time], fetch=True)
    logger.info('Found %s users for ad: %s', len(rows), ad)
    return [row["user_id"] for row in rows]


def disable_subscription_for_user(user_id):
    sql = "UPDATE users SET subscription_until = '1970-01-01' WHERE id = %s"
    execute_query(sql, [user_id])


def enable_subscription_for_user(user_id):
    sql = "UPDATE users SET subscription_until = NOW() + interval '30 days' WHERE id = %s"
    execute_query(sql, [user_id])


def get_subscription_data_for_user(user_id):
    sql = "SELECT * FROM user_filters WHERE user_id = %s"
    row = execute_query(sql, [user_id], fetchone=True)
    if row:
        return row
    else:
        return None


def round_date(date_item):
    from datetime import datetime, timedelta

    # Round up to the next day
    dt_rounded = date_item + timedelta(days=1)

    # Format in Ukrainian
    months_ukr = {
        1: "січня", 2: "лютого", 3: "березня", 4: "квітня", 5: "травня", 6: "червня",
        7: "липня", 8: "серпня", 9: "вересня", 10: "жовтня", 11: "листопада", 12: "грудня"
    }

    formatted_date = f"{dt_rounded.day} {months_ukr[dt_rounded.month]} {dt_rounded.year}р."
    print(formatted_date)
    return formatted_date


def get_subscription_until_for_user(user_id, free=False):
    sql = "SELECT subscription_until FROM users WHERE id = %s" if not free else "SELECT free_until FROM users WHERE id = %s"
    rows = execute_query(sql, [user_id], fetchone=True)
    if rows:
        # result = [row.get('free_until') or row.get('subscription_until') for row in rows]
        logger.info('Subscription until for user %s: %s', user_id, rows)
        date_obj = rows.get('free_until') or rows.get('subscription_until')
        logger.info('Subscription until for user %s: %s', user_id, date_obj)
        result = round_date(date_obj)
        logger.info('Subscription until for user %s: %s', user_id, result)
        return result
    else:
        logger.info('Subscription until for user %s: None', user_id)
        return None


def get_db_user_id_by_telegram_id(telegram_id):
    sql = "SELECT id FROM users WHERE telegram_id = %s"
    row = execute_query(sql, [telegram_id], fetchone=True)
    return row["id"] if row else None


def add_subscription(user_id, property_type, city_id, rooms_count, price_min, price_max):
    """
    Adds a new subscription row for this user.
    We assume you already checked that the user doesn't exceed 20 subscriptions.
    """
    # First, ensure the user has < 20
    sql_count = "SELECT COUNT(*) as cnt FROM user_filters WHERE user_id = %s"
    row = execute_query(sql_count, [user_id], fetchone=True)
    if row["cnt"] >= 20:
        raise ValueError("You already have 20 subscriptions, cannot add more.")

    sql_insert = """
                 INSERT INTO user_filters (user_id, property_type, city, rooms_count, price_min, price_max)
                 VALUES (%s, %s, %s, %s, %s, %s) RETURNING id \
                 """
    sub = execute_query(sql_insert, [user_id, property_type, city_id, rooms_count, price_min, price_max], fetchone=True)
    return sub["id"]


def list_subscriptions(user_id):
    sql = """
          SELECT id, property_type, city, rooms_count, price_min, price_max
          FROM user_filters
          WHERE user_id = %s
          ORDER BY id \
          """
    return execute_query(sql, [user_id], fetch=True)


def remove_subscription(subscription_id, user_id):
    """
    subscription_id is the PK in user_filters,
    user_id is the user, to ensure one user cannot remove another's subscription
    """
    sql = "DELETE FROM user_filters WHERE id = %s AND user_id = %s"
    execute_query(sql, [subscription_id, user_id])


def update_subscription(subscription_id, user_id, new_values):
    """
    new_values might be dict with property_type, city, etc.
    We'll build a small dynamic query or just do a single update if columns are fixed.
    """
    sql = """
          UPDATE user_filters
          SET property_type = %s,
              city          = %s,
              rooms_count   = %s,
              price_min     = %s,
              price_max     = %s
          WHERE id = %s
            AND user_id = %s \
          """
    params = [new_values['property_type'], new_values['city'],
              new_values['rooms_count'], new_values['price_min'], new_values['price_max'],
              subscription_id, user_id]
    execute_query(sql, params)


def add_favorite_ad(user_id, ad_id):
    # check limit 50
    sql_count = "SELECT COUNT(*) as cnt FROM favorite_ads WHERE user_id = %s"
    row = execute_query(sql_count, [user_id], fetchone=True)
    if row["cnt"] >= 50:
        raise ValueError("You already have 50 favorite ads, cannot add more.")

    sql_insert = """
                 INSERT INTO favorite_ads (user_id, ad_id)
                 VALUES (%s, %s) ON CONFLICT (user_id, ad_id) DO NOTHING -- if you have unique constraint \
                 """
    execute_query(sql_insert, [user_id, ad_id])


def list_favorites(user_id):
    sql = """
          SELECT fa.id, fa.ad_id, ads.price, ads.address, ads.city, ads.property_type, ads.rooms_count
          FROM favorite_ads fa
                   JOIN ads ON fa.ad_id = ads.id
          WHERE fa.user_id = %s
          ORDER BY fa.created_at DESC \
          """
    return execute_query(sql, [user_id], fetch=True)


def remove_favorite_ad(user_id, ad_id):
    sql = "DELETE FROM favorite_ads WHERE user_id = %s AND ad_id = %s"
    execute_query(sql, [user_id, ad_id])


def count_subscriptions(user_id):
    sql = "SELECT COUNT(*) as cnt FROM user_filters WHERE user_id = %s"
    row = execute_query(sql, [user_id], fetchone=True)
    return row["cnt"]


def list_subscriptions_paginated(user_id, page, per_page=5):
    offset = page * per_page
    sql = """
          SELECT id, city, property_type, rooms_count, price_min, price_max, is_paused
          FROM user_filters
          WHERE user_id = %s
          ORDER BY id
              LIMIT %s
          OFFSET %s \
          """
    rows = execute_query(sql, [user_id, per_page, offset], fetch=True)
    return rows


def get_extra_images(resource_url):
    # Assuming resource_url corresponds to a unique external_id or similar.
    # First, look up the ad using resource_url (or pass ad id directly instead).
    sql = "SELECT id FROM ads WHERE resource_url = %s"
    ad = execute_query(sql, [resource_url], fetchone=True)
    if not ad:
        return []
    ad_id = ad["id"]
    sql_images = "SELECT image_url FROM ad_images WHERE ad_id = %s"
    rows = execute_query(sql_images, [ad_id], fetch=True)
    return [row["image_url"] for row in rows] if rows else []


def get_full_ad_description(resource_url):
    logger.info(f'Getting full ad description for resource_url: {resource_url}...')
    sql = "SELECT description from ads WHERE resource_url = %s"
    ad = execute_query(sql, [resource_url], fetchone=True)
    return ad["description"] if ad else None


def store_ad_phones(resource_url, ad_id):
    """
    Extracts phone numbers and a viber link from the given resource URL,
    then inserts them into the ad_phones table for the given ad_id.

    Returns the number of phones stored.
    """
    # First check if the ad exists in the database
    check_sql = "SELECT id FROM ads WHERE id = %s"
    ad_exists = execute_query(check_sql, [ad_id], fetchone=True)

    if not ad_exists:
        logger.warning(f"Cannot store phones for ad_id={ad_id} - ad doesn't exist in the database")
        return 0

    # Only proceed if the ad exists
    try:
        phones_added = 0
        result = extract_phone_numbers_from_resource(resource_url)
        phones = result.phone_numbers
        viber_link = result.viber_link

        for phone in phones:
            # Double check ad exists before each insert
            if not execute_query("SELECT id FROM ads WHERE id = %s", [ad_id], fetchone=True):
                logger.warning(f"Ad {ad_id} no longer exists, aborting phone insert")
                break

            try:
                sql = "INSERT INTO ad_phones (ad_id, phone) VALUES (%s, %s)"
                execute_query(sql, [ad_id, phone])
                phones_added += 1
            except Exception as e:
                logger.error(f"Error inserting phone {phone} for ad {ad_id}: {e}")
                # Continue with other phones

        if viber_link:
            # Double check ad exists before viber link insert
            if execute_query("SELECT id FROM ads WHERE id = %s", [ad_id], fetchone=True):
                try:
                    sql = "INSERT INTO ad_phones (ad_id, viber_link) VALUES (%s, %s)"
                    execute_query(sql, [ad_id, viber_link])
                except Exception as e:
                    logger.error(f"Error inserting viber link for ad {ad_id}: {e}")

        return phones_added
    except Exception as e:
        logger.error(f"Error extracting or storing phones for ad {ad_id}: {e}")
        # Continue with the processing
        return 0


def list_favorites(user_id):
    sql = """
          SELECT fa.id,
                 fa.ad_id,
                 ads.price,
                 ads.address,
                 ads.city,
                 ads.property_type,
                 ads.rooms_count,
                 ads.resource_url,
                 ads.external_id,
                 ads.square_feet,
                 ads.floor,
                 ads.total_floors
          FROM favorite_ads fa
                   JOIN ads ON fa.ad_id = ads.id
          WHERE fa.user_id = %s
          ORDER BY fa.created_at DESC \
          """
    return execute_query(sql, [user_id], fetch=True)
