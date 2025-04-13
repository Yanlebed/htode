# services/telegram_service/app/handlers/menu_handlers.py

import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from ..bot import dp, bot
from ..states.basis_states import FilterStates
from common.db.models import update_user_filter, start_free_subscription_of_user
from common.db.database import execute_query
from common.config import GEO_ID_MAPPING, get_key_by_value, build_ad_text
from common.celery_app import celery_app
from ..keyboards import (
    main_menu_keyboard,
    how_to_use_keyboard,
    tech_support_keyboard,
    edit_parameters_keyboard
)

logger = logging.getLogger(__name__)


@dp.message_handler(commands=['menu'])
async def show_main_menu(message: types.Message):
    await message.answer(
        "Оберіть опцію:",
        reply_markup=main_menu_keyboard()
    )


# @dp.message_handler(lambda msg: msg.text == "✏️ Редагувати")
# async def handle_edit_subscription(message: types.Message):
#     user_id = message.from_user.id
#     # Show some custom flow or re-run the filter states
#     await message.answer(
#         "Давайте відредагуємо параметри. (Тут реалізуйте логіку вибору міста / кімнат...)",
#         # Possibly a different keyboard or re-use subscription_menu
#     )

@dp.message_handler(lambda msg: msg.text == "✏️ Редагувати")
async def edit_parameters(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer(
        "Оберіть параметр для редагування:",
        reply_markup=edit_parameters_keyboard()
    )
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == 'subs_back')
async def subscription_back_handler(callback_query: types.CallbackQuery):
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Повертаємося до головного меню...",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'menu_how_to_use')
async def how_to_use_handler(callback_query: types.CallbackQuery):
    text = (
        "Як використовувати:\n\n"
        "1. Налаштуйте параметри фільтра.\n"
        "2. Увімкніть передплату.\n"
        "3. Отримуйте сповіщення.\n\n"
        "Якщо у вас є додаткові питання, зверніться до служби підтримки!"
    )
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text=text,
        reply_markup=how_to_use_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'contact_support')
async def contact_support_handler(callback_query: types.CallbackQuery):
    # If you want them to message an admin directly, you can provide a link or instructions.
    # Or you can set up a separate "Support chat" logic. For simplicity:
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Напишіть своє питання, і наша служба підтримки відповість вам найближчим часом..."
    )


@dp.callback_query_handler(lambda c: c.data == 'menu_tech_support')
async def menu_tech_support_handler(callback_query: types.CallbackQuery):
    # Same as above or you can show a new keyboard
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Звернення до техпідтримки. Будь ласка, введіть своє питання.",
        reply_markup=tech_support_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'main_menu')
async def back_to_main_menu_handler(callback_query: types.CallbackQuery):
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Головне меню:",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query_handler(Text(startswith="subscribe"), state=FilterStates.waiting_for_confirmation)
async def subscribe(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    # logger.info('subscribe: user_data: %s', user_data)
    user_db_id = user_data.get('user_db_id')  # Отримуємо внутрішній ID користувача
    telegram_id = user_data.get('telegram_id')
    # logger.info('User DB ID: %s', user_db_id)
    # logger.info('Telegram ID: %s', telegram_id)

    if not user_db_id:
        await callback_query.message.answer("Ошибка: Не удалось определить вашего пользователя.")
        await callback_query.answer()
        return

    # Перетворимо дані для збереження
    filters = {
        'property_type': user_data.get('property_type'),
        'city': user_data.get('city'),
        'rooms': user_data.get('rooms'),  # Список або None
        'price_min': user_data.get('price_min'),
        'price_max': user_data.get('price_max'),
    }

    logger.info('Filters')
    logger.info(filters)

    # Збереження фільтрів у базі даних
    update_user_filter(user_db_id, filters)
    logger.info('Filters updated')
    logger.info(filters)
    start_free_subscription_of_user(user_db_id)
    logger.info('Free subscription started')
    # 1) Let user know subscription is set
    await callback_query.message.answer("Ви успішно підписалися на пошук оголошень!")

    # 2) Now do the multi-step check in local DB
    #    We'll define a helper function below or inline.
    logger.info('Fetch ads for period')
    final_ads = []
    for days_limit in [1, 3, 7, 14, 30]:
        ads = fetch_ads_for_period(filters, days_limit, limit=3)
        if len(ads) >= 1:
            final_ads = ads
            # We found enough ads => break out
            break

    if final_ads:
        # We found >=3 ads in last days_limit
        message_ending = 'день' if days_limit == 1 else 'днів'
        await callback_query.message.answer(
            f"Ось вам актуальні оголошення за останні {days_limit} {message_ending}:"
        )
        # Send them (as 3 separate messages, or combine them)
        for ad in final_ads:
            s3_image_links = get_ad_images(ad)[0]
            text = build_ad_text(ad)
            # await callback_query.message.answer(text)

            # We assume 'image_url' and 'resource_url' exist in your DB row.
            # For example, 'image_url' might be `ad.get("image_url")`
            # or 's3_image_url'.
            # 'resource_url' might be "https://flatfy.ua/uk/redirect/..."
            resource_url = ad.get("resource_url")
            # ad_id = ad.get("id")
            ad_external_id = ad.get("external_id")
            ad_id = ad.get("id")

            logger.info(f"services/telegram_service/app/handlers/menu_handlers:subscribe- Ad {ad}")
            # Now dispatch the Celery task:
            args_for_celery = [telegram_id, text, s3_image_links, resource_url, ad_id, ad_external_id]
            logger.info(
                f"services/telegram_service/app/handlers/menu_handlers:subscribe. args_for_celery task send_ad_with_extra_buttons - {args_for_celery}")
            celery_app.send_task(
                "telegram_service.app.tasks.send_ad_with_extra_buttons",
                args=args_for_celery
            )
    else:
        # We never found 3 ads even in last 30 days
        await callback_query.message.answer(
            "Ваші параметри фільтру настільки унікальні, що майже немає оголошень навіть за останній місяць.\n"
            "Спробуйте розширити параметри пошуку або зачекайте. Ми сповістимо, щойно з’являться нові оголошення."
        )

    # # 3) Optionally say: "Ми також будемо надсилати всі майбутні..."
    # await callback_query.message.answer("Ми будемо надсилати вам нові оголошення, щойно вони з’являтимуться!")

    # 4) End the state
    await state.finish()
    await callback_query.answer()

    # 5) Optional: send a task to do further real-time scraping or notification
    #    (Though you just gave them "existing" ads from the DB.)
    celery_app.send_task(
        'notifier_service.app.tasks.notify_user_with_ads',
        args=[telegram_id, filters]
    )

    await callback_query.message.answer(
        "Ми будемо надсилати вам нові оголошення, щойно вони з’являтимуться!",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == "unsubscribe", state="*")
async def unsubscribe_callback(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    # In DB, set user subscription inactive or remove user_filters
    # e.g.
    sql = "UPDATE users SET subscription_until = NOW() WHERE telegram_id = %s"
    execute_query(sql, [user_id])

    await callback_query.message.answer("Ви відписалися від розсилки оголошень.")
    await callback_query.answer()


@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='cancel', ignore_case=True), state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    """Дозволяє користувачеві скасувати будь-яку дію"""
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.finish()
    await message.answer('Дія скасована.', reply_markup=types.ReplyKeyboardRemove())


def get_ad_images(ad):
    ad_id = ad.get('id')
    sql_check = "SELECT * FROM ad_images WHERE ad_id = %s"
    rows = execute_query(sql_check, [ad_id], fetch=True)
    if rows:
        return [row["image_url"] for row in rows]


def fetch_ads_for_period(filters, days, limit=3):
    """
    Query your local ads table, matching the user’s filters,
    for ads from the last `days` days. Return up to `limit` ads.
    """
    # We assume you have a function `execute_query(sql, params, fetch=True)`
    where_clauses = []
    params = []
    city = filters.get('city')

    if city:
        where_clauses.append("city = %s")
        geo_id = get_key_by_value(city, GEO_ID_MAPPING)
        params.append(geo_id)

    if filters.get('property_type'):
        where_clauses.append("property_type = %s")
        params.append(filters['property_type'])

    if filters.get('rooms') is not None:
        # filters['rooms'] is a list, so let's match any in that list
        # E.g. rooms_count is stored as integer in "ads" table
        # We'll check "rooms_count = ANY(...)"
        where_clauses.append("rooms_count = ANY(%s)")
        params.append(filters['rooms'])

    if filters.get('price_min') is not None:
        where_clauses.append("price >= %s")
        params.append(filters['price_min'])

    if filters.get('price_max') is not None:
        where_clauses.append("price <= %s")
        params.append(filters['price_max'])

    # Now add the time window
    where_clauses.append("insert_time >= NOW() - interval '%s day'")
    params.append(days)

    # Build final WHERE
    where_sql = " AND ".join(where_clauses)
    sql = f"""
        SELECT *
        FROM ads
        WHERE {where_sql}
        ORDER BY insert_time DESC
        LIMIT {limit}
    """
    logger.info('SQL: %s', sql)
    logger.info('Params: %s', params)
    rows = execute_query(sql, params, fetch=True)
    return rows


@dp.message_handler(lambda msg: msg.text == "🤔 Як це працює?")
async def handle_how_to_use(message: types.Message):
    text = (
        "Як використовувати:\n\n"
        "1. Налаштуйте параметри фільтра.\n"
        "2. Увімкніть передплату.\n"
        "3. Отримуйте сповіщення.\n\n"
        "Якщо у вас є додаткові питання, зверніться до служби підтримки!"
    )
    await message.answer(
        text,
        reply_markup=how_to_use_keyboard()
    )


# @dp.message_handler(lambda msg: msg.text == "🧑‍💻 Техпідтримка")
# async def handle_tech_support(message: types.Message):
#     await message.answer(
#         "Служба підтримки. Введіть своє питання.",
#         reply_markup=tech_support_keyboard()
#     )


@dp.message_handler(lambda msg: msg.text == "↪️ Назад")
async def handle_back(message: types.Message):
    """
    Simple universal 'Back' handler that returns to the main menu.
    Or you can differentiate if you have multiple sub-levels.
    """
    await message.answer(
        "Повертаємося в головне меню.",
        reply_markup=main_menu_keyboard()
    )


@dp.message_handler(commands=['menu'])
async def cmd_start(message: types.Message, state: FSMContext):
    """
    Sends the main menu keyboard when the user starts or uses /menu.
    """
    await message.answer(
        "Головне меню:",
        reply_markup=main_menu_keyboard()
    )


@dp.message_handler(lambda msg: msg.text == "➕ Додати підписку")
async def edit_parameters(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer(
        "Оберіть параметр для редагування:",
        reply_markup=edit_parameters_keyboard()
    )
    await callback_query.answer()
