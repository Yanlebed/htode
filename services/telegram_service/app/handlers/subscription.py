# services/telegram_service/app/handlers/subscription.py

import logging

from aiogram import types

from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.session import db_session
from ..bot import dp, bot
from common.db.models import disable_subscription_for_user, \
    enable_subscription_for_user, get_subscription_data_for_user, get_subscription_until_for_user, \
    get_db_user_id_by_telegram_id, count_subscriptions, list_subscriptions_paginated, UserFilter
from common.db.database import execute_query
from common.config import GEO_ID_MAPPING
from ..keyboards import (
    main_menu_keyboard,
    subscription_menu_keyboard, make_subscriptions_page_kb
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)


@dp.callback_query_handler(lambda c: c.data.startswith("sub_open:"))
async def handle_sub_open(callback_query: types.CallbackQuery):
    _, sub_id_str, page_str = callback_query.data.split(":")
    sub_id = int(sub_id_str)
    page = int(page_str)

    telegram_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    # fetch the subscription using ORM
    with db_session() as db:
        sub = db.query(UserFilter).filter(
            UserFilter.id == sub_id,
            UserFilter.user_id == db_user_id
        ).first()

        if not sub:
            # subscription not found or belongs to another user
            await callback_query.answer("Підписка не знайдена.")
            return

        # Convert to dict for consistency with rest of function
        sub_dict = {
            'id': sub.id,
            'user_id': sub.user_id,
            'property_type': sub.property_type,
            'city': sub.city,
            'rooms_count': sub.rooms_count,
            'price_min': sub.price_min,
            'price_max': sub.price_max,
            'is_paused': sub.is_paused
        }

        mapping_property = {"apartment": "квартира", "house": "будинок"}
        ua_lang_property_type = mapping_property.get(sub_dict['property_type'], "")
        city = GEO_ID_MAPPING.get(sub_dict['city'])
        active = '✅ Активна' if not sub_dict['is_paused'] else '⏸️ Зупинена'
        # Build text
        text = f"Підписка #{sub_id}\n" \
               f"🏷 Тип нерухомості: {ua_lang_property_type}\n" \
               f"🏙️ Місто: {city}\n" \
               f"💰 Ціна: {sub_dict['price_min']} - {sub_dict['price_max']} грн.\n" \
               f"{active}"

        #TODO: add other options if some of them indicated

        # Build an inline keyboard with Pause/Resume, Delete, Edit, Back
        kb = InlineKeyboardMarkup()
        if sub_dict["is_paused"]:
            kb.add(InlineKeyboardButton("Відновити", callback_data=f"sub_resume:{sub_id}:{page}"))
        else:
            kb.add(InlineKeyboardButton("Зупинити", callback_data=f"sub_pause:{sub_id}:{page}"))

        kb.add(
            InlineKeyboardButton("Видалити", callback_data=f"sub_delete:{sub_id}:{page}"),
            InlineKeyboardButton("Редагувати", callback_data=f"sub_edit:{sub_id}:{page}"),
        )
        # "Back to list"
        kb.add(InlineKeyboardButton("<< Назад", callback_data=f"subs_page:{page}"))

        await callback_query.message.edit_text(text, reply_markup=kb)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("sub_pause:"))
async def handle_sub_pause(callback_query: types.CallbackQuery):
    _, sub_id_str, page_str = callback_query.data.split(":")
    sub_id = int(sub_id_str)
    page = int(page_str)

    telegram_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    with db_session() as db:
        subscription = db.query(UserFilter).filter(
            UserFilter.id == sub_id,
            UserFilter.user_id == db_user_id
        ).first()

        if subscription:
            subscription.is_paused = True
            db.commit()
            await callback_query.answer("Підписку призупинено.")
        else:
            await callback_query.answer("Підписка не знайдена.")
            return

    # Re-open subscription detail
    await handle_sub_open(callback_query)


# Refactored handler using repository
@dp.callback_query_handler(lambda c: c.data.startswith("sub_resume:"))
async def handle_sub_resume(callback_query: types.CallbackQuery):
    _, sub_id_str, page_str = callback_query.data.split(":")
    sub_id = int(sub_id_str)
    page = int(page_str)

    telegram_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    # Use repository instead of raw SQL
    with db_session() as db:
        success = SubscriptionRepository.enable_subscription_by_id(db, sub_id, db_user_id)
        if success:
            await callback_query.answer("Підписку поновлено.")
        else:
            await callback_query.answer("Підписка не знайдена.")
            return

    # Re-open subscription detail
    await handle_sub_open(callback_query)


@dp.callback_query_handler(lambda c: c.data.startswith("sub_delete:"))
async def handle_sub_delete(callback_query: types.CallbackQuery):
    _, sub_id_str, page_str = callback_query.data.split(":")
    sub_id = int(sub_id_str)
    page = int(page_str)

    telegram_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    sql = "DELETE FROM user_filters WHERE id=%s AND user_id=%s"
    execute_query(sql, [sub_id, db_user_id])
    await callback_query.answer("Підписку видалено.")

    # Return to the list view
    await handle_subs_page(callback_query)


@dp.callback_query_handler(lambda c: c.data.startswith("sub_edit:"))
async def handle_sub_edit(callback_query: types.CallbackQuery):
    _, sub_id_str, page_str = callback_query.data.split(":")
    sub_id = int(sub_id_str)
    page = int(page_str)

    # Possibly begin an FSM to ask user new city, price, etc.
    await callback_query.answer("У майбутньому тут можна відредагувати дані.")


@dp.callback_query_handler(lambda c: c.data.startswith("subs_page:"))
async def handle_subs_page(callback_query: types.CallbackQuery):
    _, page_str = callback_query.data.split(":")
    page = int(page_str)

    telegram_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    total = count_subscriptions(db_user_id)
    subs = list_subscriptions_paginated(db_user_id, page)
    kb = make_subscriptions_page_kb(db_user_id, page, subs, total)

    await callback_query.message.edit_text("Ваші підписки:", reply_markup=kb)
    await callback_query.answer()


@dp.message_handler(lambda msg: msg.text == "📝 Мої підписки")
async def show_subscriptions_menu(message: types.Message):
    telegram_id = message.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    total = count_subscriptions(db_user_id)
    if total == 0:
        await message.answer("У вас немає підписок.", reply_markup=main_menu_keyboard())
        return

    page = 0
    subs = list_subscriptions_paginated(db_user_id, page)
    kb = make_subscriptions_page_kb(db_user_id, page, subs, total)
    await message.answer("Ваші підписки:", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == 'menu_my_subscription')
async def my_subscription_handler(callback_query: types.CallbackQuery):
    # You can fetch subscription status from DB:
    user_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(user_id)
    subscription_data = get_subscription_data_for_user(db_user_id)
    subscription_valid_until = get_subscription_until_for_user(user_id)
    city = GEO_ID_MAPPING.get(subscription_data['city'])
    mapping_property = {"apartment": "Квартира", "house": "Будинок"}
    ua_lang_property_type = mapping_property.get(subscription_data['property_type'], "")

    text = f"""Деталі підписки:
     - 🏙️ Місто: {city}
     - 🏷 Тип нерухомості: {ua_lang_property_type}
     - 🛏️ Кількість кімнат: {subscription_data['rooms_count']}
     - 💰 Ціна: {str(subscription_data['price_min'])}-{str(subscription_data['price_max'])} грн.

     Підписка спливає {subscription_valid_until}
     """
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text=text,
        reply_markup=subscription_menu_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'subs_disable')
async def disable_subscription_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    # Call your DB method to disable subscription
    disable_subscription_for_user(user_id)
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Ваша підписка відключена.",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'subs_enable')
async def enable_subscription_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    enable_subscription_for_user(user_id)
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Ваша підписка включена.",
        reply_markup=main_menu_keyboard()
    )


@dp.message_handler(lambda msg: msg.text == "🛑 Відключити")
async def handle_disable_subscription(message: types.Message):
    user_id = message.from_user.id
    disable_subscription_for_user(user_id)
    await message.answer(
        "Ваша підписка відключена.",
        reply_markup=main_menu_keyboard()
    )


@dp.message_handler(lambda msg: msg.text == "✅ Включити")
async def handle_enable_subscription(message: types.Message):
    user_id = message.from_user.id
    enable_subscription_for_user(user_id)
    await message.answer(
        "Ваша підписка включена на безкоштовний період (або на платний, якщо ви вже оплачували).",
        reply_markup=main_menu_keyboard()
    )


@dp.message_handler(lambda msg: msg.text == "📝 Моя підписка")
async def handle_my_subscription(message: types.Message):
    """
    Show subscription details & sub-menu keyboard.
    """
    user_id = message.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(user_id)
    logger.info('User ID handle_my_subscription: %s', user_id)
    logger.info('DB User ID handle_my_subscription: %s', db_user_id)
    # Suppose get_subscription_data_for_user returns details from the DB
    sub_data = get_subscription_data_for_user(db_user_id)
    subscription_until = get_subscription_until_for_user(db_user_id, free=True)
    if not subscription_until:
        subscription_until = get_subscription_until_for_user(db_user_id, free=False)

    city = GEO_ID_MAPPING.get(sub_data['city'])
    mapping_property = {"apartment": "Квартира", "house": "Будинок"}
    ua_lang_property_type = mapping_property.get(sub_data['property_type'], "")
    rooms_list = sub_data['rooms_count']
    rooms = []
    for el in rooms_list:
        rooms += str(el)
    rooms = '-'.join(rooms)
    if sub_data:
        text = (
            f"Деталі підписки:\n"
            f"  - Місто: {city}\n"
            f"  - Тип нерухомості: {ua_lang_property_type}\n"
            f"  - К-сть кімнат: {rooms}\n"
            f"  - Ціна: {str(sub_data['price_min'])} - {str(sub_data['price_max'])} грн.\n\n"
            f"Підписка спливає {subscription_until}\n"
        )
    else:
        text = "У вас немає активної підписки."

    await message.answer(
        text,
        reply_markup=subscription_menu_keyboard()
    )
