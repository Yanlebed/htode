# services/telegram_service/app/handlers.py
import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import ParseMode
from .bot import dp, bot
from .states import FilterStates
from .keyboards import (
    property_type_keyboard, city_keyboard, rooms_keyboard,
    price_keyboard, listing_date_keyboard, confirmation_keyboard,
    edit_parameters_keyboard
)
from common.db.models import get_or_create_user, update_user_filter, get_user_filters, disable_subscription_for_user, \
    enable_subscription_for_user, get_subscription_data_for_user, get_subscription_until_for_user
from common.celery_app import celery_app  # Импортируем общий Celery экземпляр
from .keyboards import (
    main_menu_keyboard,
    subscription_menu_keyboard,
    how_to_use_keyboard,
    tech_support_keyboard
)

# Список доступных городов (можно получить из базы данных или конфигурации)
AVAILABLE_CITIES = ["Киев", "Харьков", "Одесса", "Днепр", "Львов"]


@dp.message_handler(commands=['start'])
async def start_command(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    user_db_id = get_or_create_user(telegram_id)  # Получаем внутренний id пользователя

    await message.answer(
        "Привет! Я бот по поиску объявлений.\n"
        "У вас сейчас активен бесплатный период 7 дней.\n"
        "Давайте настроим ваши параметры поиска.",
        reply_markup=property_type_keyboard()
    )
    await FilterStates.waiting_for_property_type.set()

    # Сохраняем user_db_id в состоянии, чтобы использовать его позже
    await state.update_data(user_db_id=user_db_id, telegram_id=telegram_id)


@dp.message_handler(commands=['menu'])
async def show_main_menu(message: types.Message):
    await message.answer(
        "Выбери опцию:",
        reply_markup=main_menu_keyboard()
    )


"""
CREATE TABLE IF NOT EXISTS user_filters (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    property_type VARCHAR(50),
    city VARCHAR(255),
    rooms_count INTEGER[] NOT NULL,
    price_min NUMERIC,
    price_max NUMERIC,
    listing_date VARCHAR(50)
);

"""


@dp.callback_query_handler(lambda c: c.data == 'menu_my_subscription')
async def my_subscription_handler(callback_query: types.CallbackQuery):
    # You can fetch subscription status from DB:
    user_id = callback_query.from_user.id
    subscription_data = get_subscription_data_for_user(user_id)
    subscription_valid_until = get_subscription_until_for_user(user_id)
    text = f"""Детали подписки:
    - Город: {subscription_data['city']}
    - Тип недвижимости: {subscription_data['property_type']}
    - Количество комнат: {subscription_data['rooms_count']}
    - Цена: {subscription_data['price_min']}-{subscription_data['price_max']}
    
    Подписка активна до {subscription_valid_until}
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
        text="Ваша подписка отключена.",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'subs_enable')
async def enable_subscription_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    enable_subscription_for_user(user_id)
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Ваша подписка включена.",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'subs_edit')
async def edit_subscription_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Давайте отредактируем параметры вашей подписки...",
        # Maybe show some filters, etc.
    )


@dp.callback_query_handler(lambda c: c.data == 'subs_back')
async def subscription_back_handler(callback_query: types.CallbackQuery):
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Возвращаемся в главное меню...",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'menu_how_to_use')
async def how_to_use_handler(callback_query: types.CallbackQuery):
    text = (
        "Как использовать:\n\n"
        "1. Настройте параметры фильтра.\n"
        "2. Включите подписку.\n"
        "3. Получайте уведомления.\n\n"
        "Если у вас есть дополнительные вопросы, свяжитесь со службой поддержки!"
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
        text="Напишите свой вопрос, и наша служба поддержки ответит вам в ближайшее время..."
    )


@dp.callback_query_handler(lambda c: c.data == 'menu_tech_support')
async def menu_tech_support_handler(callback_query: types.CallbackQuery):
    # Same as above or you can show a new keyboard
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Обращение в техподдержку. Пожалуйста, введите свой вопрос.",
        reply_markup=tech_support_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data == 'main_menu')
async def back_to_main_menu_handler(callback_query: types.CallbackQuery):
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Главное меню:",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('property_type_'),
                           state=FilterStates.waiting_for_property_type)
async def process_property_type(callback_query: types.CallbackQuery, state: FSMContext):
    property_type = callback_query.data.split('_')[-1]
    await state.update_data(property_type=property_type)

    await callback_query.message.answer(
        "Выберите город:",
        reply_markup=city_keyboard(AVAILABLE_CITIES)
    )
    await FilterStates.waiting_for_city.set()
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('city_'), state=FilterStates.waiting_for_city)
async def process_city(callback_query: types.CallbackQuery, state: FSMContext):
    city = callback_query.data.split('_', 1)[1].capitalize()
    if city not in AVAILABLE_CITIES:
        await callback_query.message.answer("Пожалуйста, выберите город из предложенного списка.")
        return
    await state.update_data(city=city)

    await callback_query.message.answer(
        "Выберите количество комнат (можно выбрать несколько):",
        reply_markup=rooms_keyboard()
    )
    await FilterStates.waiting_for_rooms.set()
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('rooms_'), state=FilterStates.waiting_for_rooms)
async def process_rooms(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data
    user_data = await state.get_data()
    selected_rooms = user_data.get('rooms', [])

    if data == 'rooms_done':
        if not selected_rooms:
            await callback_query.message.answer("Вы не выбрали количество комнат.")
            return
        await callback_query.message.answer(
            "Выберите диапазон цен:",
            reply_markup=price_keyboard()
        )
        await FilterStates.waiting_for_price.set()
        await callback_query.answer()
    elif data == 'rooms_any':
        await state.update_data(rooms=None)
        await callback_query.message.answer(
            "Выберите диапазон цен:",
            reply_markup=price_keyboard()
        )
        await FilterStates.waiting_for_price.set()
        await callback_query.answer()
    elif data.startswith('rooms_'):
        try:
            rooms_number = int(data.split('_')[1])
            if rooms_number in selected_rooms:
                selected_rooms.remove(rooms_number)
            else:
                selected_rooms.append(rooms_number)
            await state.update_data(rooms=selected_rooms)

            # Обновляем клавиатуру, показывая выбранные комнаты
            await callback_query.message.edit_reply_markup(reply_markup=rooms_keyboard(selected_rooms))
            await callback_query.answer()
        except (IndexError, ValueError):
            await callback_query.message.answer("Произошла ошибка при выборе комнат.")
            await callback_query.answer()
    else:
        await callback_query.message.answer("Неизвестная команда.")
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('price_'), state=FilterStates.waiting_for_price)
async def process_price(callback_query: types.CallbackQuery, state: FSMContext):
    price_data = callback_query.data.split('_')[-2:]
    if price_data[-1] == "any":
        price_min, price_max = 1500, None
    else:
        try:
            price_min, price_max = map(int, price_data)
        except ValueError:
            await callback_query.message.answer("Некорректный диапазон цен.")
            await callback_query.answer()
            return

    await state.update_data(price_min=price_min, price_max=price_max)

    await callback_query.message.answer(
        "Выберите дату размещения объявлений:",
        reply_markup=listing_date_keyboard()
    )
    await FilterStates.waiting_for_listing_date.set()
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('date_'), state=FilterStates.waiting_for_listing_date)
async def process_listing_date(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data
    if data == 'date_today':
        listing_date = 'today'
    elif data == 'date_3_days':
        listing_date = '3_days'
    elif data == 'date_week':
        listing_date = 'week'
    elif data == 'date_month':
        listing_date = 'month'
    elif data == 'date_all_time':
        listing_date = 'all_time'
    else:
        listing_date = 'all_time'

    await state.update_data(listing_date=listing_date)

    # Получение всех данных из состояния
    user_data = await state.get_data()
    logging.info('process_listing_date: user_data: %s', user_data)
    property_type = user_data.get('property_type').capitalize()
    city = user_data.get('city')
    rooms = ', '.join(map(str, user_data.get('rooms'))) if user_data.get('rooms') else 'Не важно'

    # Определение диапазона цен
    price_min = user_data.get('price_min')
    price_max = user_data.get('price_max')
    if price_min and price_max:
        price_range = f"{price_min}$ - {price_max}$"
    elif price_min and not price_max:
        price_range = f"Более {price_min}$"
    elif not price_min and price_max:
        price_range = f"До {price_max}$"
    else:
        price_range = "Не важно"

    # Маппинг 'listing_date' на отображаемую строку без подчеркиваний
    display_listing_date = {
        'today': 'Сегодня',
        '3_days': 'Последние 3 дня',
        'week': 'Последняя неделя',
        'month': 'Последний месяц',
        'all_time': 'Все время'
    }.get(listing_date, 'Не важно')

    summary = (
        f"**Параметры поиска:**\n"
        f"Тип недвижимости: {property_type}\n"
        f"Город: {city}\n"
        f"Количество комнат: {rooms}\n"
        f"Диапазон цен: {price_range}\n"
        f"Дата размещения: {display_listing_date}"
    )

    # Экранирование специальных символов в сообщении Markdown
    from aiogram.utils.markdown import escape_md
    summary_escaped = escape_md(summary)

    await callback_query.message.answer(
        summary_escaped,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=confirmation_keyboard()
    )
    await FilterStates.waiting_for_confirmation.set()
    await callback_query.answer()


@dp.callback_query_handler(Text(startswith="edit_parameters"), state=FilterStates.waiting_for_confirmation)
async def edit_parameters(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer(
        "Выберите параметр для редактирования:",
        reply_markup=edit_parameters_keyboard()
    )
    await callback_query.answer()


@dp.callback_query_handler(Text(startswith="subscribe"), state=FilterStates.waiting_for_confirmation)
async def subscribe(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    logging.info('subscribe: user_data: %s', user_data)
    user_db_id = user_data.get('user_db_id')  # Получаем внутренний id пользователя
    telegram_id = user_data.get('telegram_id')
    logging.info('User DB ID: %s', user_db_id)

    if not user_db_id:
        await callback_query.message.answer("Ошибка: Не удалось определить вашего пользователя.")
        await callback_query.answer()
        return

    # Преобразуем данные для сохранения
    filters = {
        'property_type': user_data.get('property_type'),
        'city': user_data.get('city'),
        'rooms': user_data.get('rooms'),  # Список или None
        'price_min': user_data.get('price_min'),
        'price_max': user_data.get('price_max'),
        'listing_date': user_data.get('listing_date')
    }

    # Сохранение фильтров в базе данных
    update_user_filter(user_db_id, filters)

    await callback_query.message.answer("Вы успешно подписались на поиск объявлений!")
    await state.finish()
    await callback_query.answer()

    # Отправка задачи notify_user_with_ads через общий Celery экземпляр
    celery_app.send_task(
        'notifier_service.app.tasks.notify_user_with_ads',
        args=[telegram_id, filters]
    )


@dp.callback_query_handler(Text(startswith="edit_"), state=FilterStates.waiting_for_confirmation)
async def handle_edit(callback_query: types.CallbackQuery, state: FSMContext):
    edit_field = callback_query.data.split('_', 1)[1]

    if edit_field == "property_type":
        await callback_query.message.answer(
            "Выберите тип недвижимости:",
            reply_markup=property_type_keyboard()
        )
        await FilterStates.waiting_for_property_type.set()
    elif edit_field == "city":
        await callback_query.message.answer(
            "Выберите город:",
            reply_markup=city_keyboard(AVAILABLE_CITIES)
        )
        await FilterStates.waiting_for_city.set()
    elif edit_field == "rooms":
        user_data = await state.get_data()
        selected_rooms = user_data.get('rooms', [])
        await callback_query.message.answer(
            "Выберите количество комнат (можно выбрать несколько):",
            reply_markup=rooms_keyboard(selected_rooms)
        )
        await FilterStates.waiting_for_rooms.set()
    elif edit_field == "price":
        await callback_query.message.answer(
            "Выберите диапазон цен:",
            reply_markup=price_keyboard()
        )
        await FilterStates.waiting_for_price.set()
    elif edit_field == "listing_date":
        await callback_query.message.answer(
            "Выберите дату размещения объявлений:",
            reply_markup=listing_date_keyboard()
        )
        await FilterStates.waiting_for_listing_date.set()
    elif edit_field == "cancel_edit":
        await callback_query.message.answer("Редактирование отменено.", reply_markup=confirmation_keyboard())
        await FilterStates.waiting_for_confirmation.set()
    else:
        await callback_query.message.answer("Неизвестный параметр для редактирования.")

    await callback_query.answer()


@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='cancel', ignore_case=True), state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    """Позволяет пользователю отменить любое действие"""
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.finish()
    await message.answer('Действие отменено.', reply_markup=types.ReplyKeyboardRemove())
