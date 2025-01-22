# common/db/models.py

from .database import execute_query
import datetime
import logging


def get_or_create_user(telegram_id):
    logging.info("Getting user with telegram id: %s", telegram_id)
    sql_check = "SELECT id FROM users WHERE telegram_id = %s"
    row = execute_query(sql_check, [telegram_id], fetchone=True)
    if row:
        logging.info("Found user with telegram id: %s", telegram_id)
        return row['id']

    logging.info("Creating user with telegram id: %s", telegram_id)
    free_until = (datetime.datetime.now() + datetime.timedelta(days=7)).isoformat()
    sql_insert = """
    INSERT INTO users (telegram_id, free_until)
    VALUES (%s, %s)
    RETURNING id
    """
    user = execute_query(sql_insert, [telegram_id, free_until], fetchone=True)
    return user['id']


def update_user_filter(user_id, filters):
    property_type = filters.get('property_type')
    city = filters.get('city')
    rooms_count = filters.get('rooms')  # Это теперь список или None
    price_min = filters.get('price_min')
    price_max = filters.get('price_max')
    listing_date = filters.get('listing_date')

    sql_upsert = """
    INSERT INTO user_filters (user_id, property_type, city, rooms_count, price_min, price_max, listing_date)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (user_id)
    DO UPDATE SET
        property_type = EXCLUDED.property_type,
        city = EXCLUDED.city,
        rooms_count = EXCLUDED.rooms_count,
        price_min = EXCLUDED.price_min,
        price_max = EXCLUDED.price_max,
        listing_date = EXCLUDED.listing_date
    """
    execute_query(sql_upsert, [user_id, property_type, city, rooms_count, price_min, price_max, listing_date])


def get_user_filters(user_id):
    sql = "SELECT * FROM user_filters WHERE user_id = %s"
    rows = execute_query(sql, [user_id], fetch=True)
    return rows[0] if rows else None


def find_users_for_ad(ad):
    """
    Возвращает список user_id, которым подходит объявление.
    """
    sql = """
    SELECT u.id AS user_id, uf.property_type, uf.city, uf.rooms_count, uf.price_min, uf.price_max, uf.listing_date
    FROM user_filters uf
    JOIN users u ON uf.user_id = u.id
    WHERE
      (u.free_until > NOW() OR (u.subscription_until > NOW()))
      AND (uf.property_type = %s OR uf.property_type IS NULL)
      AND (uf.city = %s OR uf.city IS NULL)
      AND (uf.rooms_count = %s OR uf.rooms_count IS NULL)
      AND (uf.price_min IS NULL OR ad.price >= uf.price_min)
      AND (uf.price_max IS NULL OR ad.price <= uf.price_max)
      AND (
            uf.listing_date = 'all_time'
            OR (uf.listing_date = 'today' AND ad.insert_time >= NOW()::date)
            OR (uf.listing_date = '3_days' AND ad.insert_time >= NOW()::date - interval '3 days')
            OR (uf.listing_date = 'week' AND ad.insert_time >= NOW()::date - interval '7 days')
            OR (uf.listing_date = 'month' AND ad.insert_time >= NOW()::date - interval '30 days')
          )
    """
    # Предполагается, что в `ads` есть соответствующие поля
    # Выполните SQL-запрос с передачей параметров объявления
    # Пример:
    ad_property_type = ad.get('property_type')
    ad_city = ad.get('city')
    ad_rooms = ad.get('rooms_count')
    ad_price = ad.get('price')
    ad_insert_time = ad.get('insert_time')

    # Преобразование listing_date для SQL-запроса
    # Это должно соответствовать формату, который вы используете
    # Например: 'today', '3_days', 'week', 'month', 'all_time'

    # Выполняем SQL-запрос
    rows = execute_query(sql, [ad_property_type, ad_city, ad_rooms, ad_price, ad_price, ad_insert_time], fetch=True)
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

def get_subscription_until_for_user(user_id):
    sql = "SELECT subscription_until FROM users WHERE id = %s"
    row = execute_query(sql, [user_id], fetchone=True)
    if row:
        return row['subscription_until']
    else:
        return None