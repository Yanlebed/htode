# services/telegram_service/app/handlers.py
import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import ParseMode
from aiogram.utils.exceptions import MessageNotModified
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .bot import dp, bot
from .states import FilterStates
from .keyboards import (
    property_type_keyboard, city_keyboard, rooms_keyboard,
    price_keyboard, confirmation_keyboard,
    edit_parameters_keyboard, floor_keyboard
)
from common.db.models import get_or_create_user, update_user_filter, get_user_filters, disable_subscription_for_user, \
    enable_subscription_for_user, get_subscription_data_for_user, get_subscription_until_for_user
from common.db.database import execute_query
from common.celery_app import celery_app  # Імпортуємо загальний Celery екземпляр
from .keyboards import (
    main_menu_keyboard,
    subscription_menu_keyboard,
    how_to_use_keyboard,
    tech_support_keyboard
)

# Список доступних міст (можна отримати з бази даних або конфігурації)
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


@dp.message_handler(commands=['start'])
async def start_command(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    user_db_id = get_or_create_user(telegram_id)  # Отримуємо внутрішній id користувача

    await message.answer(
        "Привіт! Я бот з пошуку оголошень.\n"
        "У вас зараз активний безкоштовний період 7 днів.\n"
        "Давайте налаштуємо ваші параметри пошуку.",
        reply_markup=property_type_keyboard()
    )
    await FilterStates.waiting_for_property_type.set()

    # Сохраняем user_db_id в состоянии, чтобы использовать его позже
    await state.update_data(user_db_id=user_db_id, telegram_id=telegram_id)


@dp.message_handler(commands=['menu'])
async def show_main_menu(message: types.Message):
    await message.answer(
        "Оберіть опцію:",
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
);

"""


@dp.callback_query_handler(lambda c: c.data == 'menu_my_subscription')
async def my_subscription_handler(callback_query: types.CallbackQuery):
    # You can fetch subscription status from DB:
    user_id = callback_query.from_user.id
    subscription_data = get_subscription_data_for_user(user_id)
    subscription_valid_until = get_subscription_until_for_user(user_id)
    text = f"""Деталі підписки:
     - Місто: {subscription_data['city']}
     - Тип нерухомості: {subscription_data['property_type']}
     - Кількість кімнат: {subscription_data['rooms_count']}
     - Ціна: {subscription_data['price_min']}-{subscription_data['price_max']}

     Підписка активна до {subscription_valid_until}
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


@dp.callback_query_handler(lambda c: c.data == 'subs_edit')
async def edit_subscription_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="Давайте відредагуємо параметри вашої підписки.",
        # Maybe show some filters, etc.
    )


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


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('property_type_'),
                           state=FilterStates.waiting_for_property_type)
async def process_property_type(callback_query: types.CallbackQuery, state: FSMContext):
    property_type = callback_query.data.split('_')[-1]
    await state.update_data(property_type=property_type)

    await callback_query.message.answer(
        "Оберіть місто:",
        reply_markup=city_keyboard(AVAILABLE_CITIES)
    )
    await FilterStates.waiting_for_city.set()
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('city_'), state=FilterStates.waiting_for_city)
async def process_city(callback_query: types.CallbackQuery, state: FSMContext):
    city = callback_query.data.split('_', 1)[1].capitalize()
    if city not in AVAILABLE_CITIES:
        await callback_query.message.answer("Будь ласка, оберіть місто зі списку.")
        return
    await state.update_data(city=city)

    await callback_query.message.answer(
        "Виберіть кількість кімнат (можна обрати декілька):",
        reply_markup=rooms_keyboard()
    )
    await FilterStates.waiting_for_rooms.set()
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('rooms_'), state=FilterStates.waiting_for_rooms)
async def process_rooms(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data
    user_data = await state.get_data()
    city = user_data.get('city')
    selected_rooms = user_data.get('rooms', [])

    if data == 'rooms_done':
        if not selected_rooms:
            await callback_query.message.answer("Ви не обрали кількість кімнат.")
            return
        await callback_query.message.answer(
            "Виберіть діапазон цін:",
            reply_markup=price_keyboard(city=city)
        )
        await FilterStates.waiting_for_price.set()
        await callback_query.answer()
    elif data == 'rooms_any':
        await state.update_data(rooms=None)
        await callback_query.message.answer(
            "Виберіть діапазон цін:",
            reply_markup=price_keyboard(city=city)
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
            await callback_query.message.answer("Виникла помилка при виборі кількості кімнат.")
            await callback_query.answer()
    else:
        await callback_query.message.answer("Невідома команда.")
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('price_'), state=FilterStates.waiting_for_price)
async def process_price(callback_query: types.CallbackQuery, state: FSMContext):
    # callback_query.data might look like "price_0_5000" or "price_5000_7000" or "price_15000_any"
    parts = callback_query.data.split("_")
    if len(parts) == 3 and parts[2] == "any":
        low = int(parts[1])  # 15000
        high = None
    else:
        low = int(parts[1])
        high = int(parts[2])

    text_range = f"{low}+ грн." if not high else f"{low}–{high} грн."
    await callback_query.message.answer(f"Ви обрали діапазон: {text_range}")

    await state.update_data(price_min=low, price_max=high)

    # Instead of waiting for a new button press, call the "process_basic_params"
    # function directly, so it shows the summary + confirmation buttons.
    await process_basic_params(callback_query, state)

    # Mark it done, so we are now in waiting_for_confirmation
    # (Inside process_basic_params you set waiting_for_confirmation,
    #  so no need to set it again here.)
    await callback_query.answer()



@dp.callback_query_handler(lambda c: c.data and c.data.startswith('confirmation_'), state=FilterStates.waiting_for_basic_params)
async def process_basic_params(callback_query: types.CallbackQuery, state: FSMContext):
    # Получение всех данных из состояния
    logging.info('process_basic_params: state: %s', await state.get_data())
    user_data = await state.get_data()
    property_type = user_data.get('property_type').capitalize()
    city = user_data.get('city')
    rooms = ', '.join(map(str, user_data.get('rooms'))) if user_data.get('rooms') else 'Не важливо'

    # Определение диапазона цен
    price_min = user_data.get('price_min')
    price_max = user_data.get('price_max')
    if price_min and price_max:
        price_range = f"{price_min}-{price_max} грн."
    elif price_min and not price_max:
        price_range = f"Більше {price_min} грн."
    elif not price_min and price_max:
        price_range = f"До {price_max} грн."
    else:
        price_range = "Не важливо"

    summary = (
        f"**Обрані параметри пошуку:**\n"
        f"Тип нерухомості: {property_type}\n"
        f"Місто: {city}\n"
        f"Кількість кімнат: {rooms}\n"
        f"Діапазон цін: {price_range}\n"
    )

    # Екранування спеціальних символів у повідомленні Markdown
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
    user_db_id = user_data.get('user_db_id')  # Отримуємо внутрішній ID користувача
    telegram_id = user_data.get('telegram_id')
    logging.info('User DB ID: %s', user_db_id)

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

    # Збереження фільтрів у базі даних
    update_user_filter(user_db_id, filters)

    await callback_query.message.answer("Ви успішно підписалися на пошук оголошень!")
    await callback_query.message.answer("А поки будуть з’являтися нові оголошення, ось вам оголошення за сьогодні:")
    await state.finish()
    await callback_query.answer()

    # Надсилання завдання notify_user_with_ads через загальний Celery екземпляр
    celery_app.send_task(
        'notifier_service.app.tasks.notify_user_with_ads',
        args=[telegram_id, filters]
    )


@dp.callback_query_handler(Text(startswith="edit_"), state=FilterStates.waiting_for_confirmation)
async def handle_edit(callback_query: types.CallbackQuery, state: FSMContext):
    logging.info('handle_edit: callback_query: %s', callback_query)
    edit_field = callback_query.data.split('_', 1)[1]
    user_data = await state.get_data()
    city = user_data.get('city')

    if edit_field == "property_type":
        await callback_query.message.answer(
            "Оберіть тип нерухомості:",
            reply_markup=property_type_keyboard()
        )
        await FilterStates.waiting_for_property_type.set()
    elif edit_field == "city":
        await callback_query.message.answer(
            "Оберіть місто:",
            reply_markup=city_keyboard(AVAILABLE_CITIES)
        )
        await FilterStates.waiting_for_city.set()
    elif edit_field == "rooms":
        user_data = await state.get_data()
        selected_rooms = user_data.get('rooms', [])
        await callback_query.message.answer(
            "Виберіть кількість кімнат (можна вибрати декілька):",
            reply_markup=rooms_keyboard(selected_rooms)
        )
        await FilterStates.waiting_for_rooms.set()
    elif edit_field == "price":
        await callback_query.message.answer(
            "Виберіть діапазон цін:",
            reply_markup=price_keyboard(city=city)
        )
        await FilterStates.waiting_for_price.set()
    elif edit_field == "floor":
        # call your function to handle floor editing
        await callback_query.message.answer("!!!Налаштуйте поверх:", reply_markup=floor_keyboard())
        # optionally change state, etc.
    elif edit_field == "cancel_edit":
        await callback_query.message.answer("Редагування скасовано.", reply_markup=confirmation_keyboard())
        await FilterStates.waiting_for_confirmation.set()
    else:
        await callback_query.message.answer("Невідомий параметр редагування.")

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


async def show_advanced_options(message: types.Message, state: FSMContext):
    # Build a keyboard for advanced fields
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Поверх", callback_data="edit_floor"),
    )
    keyboard.add(
        InlineKeyboardButton("З тваринами?", callback_data="pets_allowed"),
    )
    keyboard.add(
        InlineKeyboardButton("Від власника?", callback_data="without_broker"),
    )
    # "Готово" -> return to summary
    keyboard.add(InlineKeyboardButton("Повернутись назад", callback_data="advanced_done"))

    await message.answer("Оберіть параметр для зміни:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == "advanced_search", state=FilterStates.waiting_for_confirmation)
async def advanced_search_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_floor_max", state="*")
async def edit_floor_max_handler(callback_query: types.CallbackQuery, state: FSMContext):
    # Show some example floors from 1..25 or 1..10
    keyboard = InlineKeyboardMarkup(row_width=5)
    floors = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # Adjust as you like
    for f in floors:
        keyboard.insert(InlineKeyboardButton(str(f), callback_data=f"floor_max_{f}"))
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Виберіть максимальний поверх:", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("floor_max_"), state="*")
async def set_floor_max(callback_query: types.CallbackQuery, state: FSMContext):
    # parse the chosen floor
    chosen_floor = int(callback_query.data.split("_")[2])  # "floor_max_6" -> 6
    await state.update_data(floor_max=chosen_floor)

    await callback_query.message.answer(f"Максимальний поверх тепер {chosen_floor}.")
    # Optionally show advanced menu again
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "return_to_advanced_menu", state="*")
async def return_to_advanced_menu_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_is_not_first_floor", state="*")
async def edit_is_not_first_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Так", callback_data="is_not_first_floor_yes"))
    keyboard.add(InlineKeyboardButton("Ні", callback_data="is_not_first_floor_no"))
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Чи виключати перший поверх?", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("is_not_first_floor_"), state="*")
async def set_is_not_first_floor(callback_query: types.CallbackQuery, state: FSMContext):
    # either "yes" or "no"
    value = callback_query.data.split("_")[-1]  # yes / no
    # The actual param for flatfy would be `is_not_first_floor=yes` or `no`
    await state.update_data(is_not_first_floor=value)

    text = "Виключаю перший поверх" if value == "yes" else "Перший поверх дозволений"
    await callback_query.message.answer(text)
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_last_floor", state="*")
async def edit_last_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Так", callback_data="last_floor_yes"),
        InlineKeyboardButton("Ні", callback_data="last_floor_no")
    )
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Виключати останній поверх?", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("last_floor_"), state="*")
async def set_last_floor(callback_query: types.CallbackQuery, state: FSMContext):
    value = callback_query.data.split("_")[-1]  # yes / no
    await state.update_data(last_floor=value)

    text = "Виключаю останній поверх" if value == "no" else "Тільки останній поверх"
    # Actually, for flatfy: "last_floor=no" means do not show last floor ads?
    await callback_query.message.answer(f"last_floor={value}")
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "pets_allowed", state="*")
async def edit_pets_allowed_handler(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Так (yes)", callback_data="pets_allowed_yes"),
        InlineKeyboardButton("Ні (no)", callback_data="pets_allowed_no"),
        InlineKeyboardButton("Деякі (some)", callback_data="pets_allowed_some"),
    )
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Чи дозволені тварини?", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("pets_allowed_"), state="*")
async def set_pets_allowed(callback_query: types.CallbackQuery, state: FSMContext):
    value = callback_query.data.split("_")[-1]  # yes / no / some
    await state.update_data(pets_allowed_full=value)

    await callback_query.message.answer(f"Обрано: {value}")
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "without_broker", state="*")
async def edit_without_broker_handler(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Від власника", callback_data="without_broker_owner"),
        InlineKeyboardButton("Усі оголошення", callback_data="without_broker_all")
    )
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Виберіть вид оголошень:", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("without_broker_"), state="*")
async def set_without_broker(callback_query: types.CallbackQuery, state: FSMContext):
    choice = callback_query.data.split("_")[-1]  # "owner" or "all"
    if choice == "owner":
        await state.update_data(without_broker="owner")
        text = "Тільки від власника"
    else:
        await state.update_data(without_broker=None)  # or just remove param
        text = "Усі оголошення"

    await callback_query.message.answer(text)
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


def build_full_summary(data: dict) -> str:
    property_type = data.get("property_type", "")
    city = data.get("city", "")
    rooms = data.get("rooms", [])  # list
    price_min = data.get("price_min")
    price_max = data.get("price_max")

    floor_max = data.get("floor_max")
    is_not_first_floor = data.get("is_not_first_floor")
    last_floor = data.get("last_floor")
    pets_allowed_full = data.get("pets_allowed_full")
    without_broker = data.get("without_broker")

    # build lines
    lines = []
    lines.append(f"Тип нерухомості: {property_type}")
    lines.append(f"Місто: {city}")
    lines.append(f"Кімнат: {', '.join(map(str, rooms)) if rooms else 'Не важливо'}")

    # Price range
    if price_min and price_max:
        lines.append(f"Ціновий діапазон: {price_min} - {price_max} UAH")
    elif price_min and not price_max:
        lines.append(f"Від {price_min} UAH")
    elif price_max and not price_min:
        lines.append(f"До {price_max} UAH")
    else:
        lines.append("Ціна: не важливо")

    # ADVANCED
    if floor_max:
        lines.append(f"Поверхи до: {floor_max}")
    if is_not_first_floor == "yes":
        lines.append("Не перший поверх")
    elif is_not_first_floor == "no":
        lines.append("Перший поверх дозволено")

    if last_floor == "yes":
        lines.append("Тільки останній поверх")
    elif last_floor == "no":
        lines.append("Останній поверх виключено")

    if pets_allowed_full:
        lines.append(f"Тварини: {pets_allowed_full}")

    if without_broker == "owner":
        lines.append("Тільки від власника")
    else:
        lines.append("Усі оголошення (брокери + власники)")

    return "**Поточні параметри пошуку**\n" + "\n".join(lines)


@dp.callback_query_handler(lambda c: c.data == "advanced_done", state="*")
async def advanced_done_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    summary = build_full_summary(user_data)  # We'll define build_full_summary below

    from aiogram.utils.markdown import escape_md
    summary_escaped = escape_md(summary)

    # A new keyboard that shows "Редагувати" or "Підписатися"
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("Редагувати", callback_data="edit_parameters"),
        InlineKeyboardButton("Підписатися", callback_data="subscribe"),
    )

    await callback_query.message.answer(summary_escaped, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_floor", state="*")
async def edit_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    logging.info('in edit_floor_handler')
    user_data = await state.get_data()
    floor_opts = user_data.get("floor_opts", {
        "not_first": False,
        "not_last": False,
        "floor_max_6": False,
        "floor_max_10": False,
        "floor_max_17": False,
        "only_last": False
    })
    await state.update_data(floor_opts=floor_opts)

    kb = floor_keyboard(floor_opts)
    await callback_query.message.answer("Налаштуйте поверх:", reply_markup=kb)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("toggle_floor_"), state="*")
async def toggle_floor_callback(callback_query: types.CallbackQuery, state: FSMContext):
    # e.g. toggle_floor_not_first, toggle_floor_only_last, toggle_floor_6 ...
    logging.info('in toggle_floor_callback')
    choice = callback_query.data.split("_", 2)[-1]  # "not_first", "not_last", "only_last", "6", "10", "17"
    user_data = await state.get_data()
    floor_opts = user_data.get("floor_opts", {
        "not_first": False,
        "not_last": False,
        "floor_max_6": False,
        "floor_max_10": False,
        "floor_max_17": False,
        "only_last": False
    })

    current_val = floor_opts.get(choice, False)
    new_val = not current_val
    floor_opts[choice] = new_val

    # Contradictions
    if choice == "only_last" and new_val is True:
        floor_opts["not_last"] = False
    if choice == "not_last" and new_val is True:
        floor_opts["only_last"] = False

    if choice in ["6", "10", "17"] and new_val is True:
        for other in ["6", "10", "17"]:
            if other != choice:
                floor_opts[f"floor_max_{other}"] = False

    await state.update_data(floor_opts=floor_opts)

    kb = floor_keyboard(floor_opts)  # ensure floor_keyboard also uses "not_first", "not_last", etc.

    try:
        await callback_query.message.edit_text(
            "Налаштуйте поверх:",
            reply_markup=kb
        )
    except MessageNotModified:
        await callback_query.answer("Немає змін.")

    await callback_query.answer()


def floor_opts_key(num_str):
    return f"floor_max_{num_str}"


@dp.callback_query_handler(lambda c: c.data == "floor_done", state="*")
async def floor_done_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    floor_opts = user_data.get("floor_opts", {})

    # Convert toggles to final fields
    # For example:
    #  - is_not_first_floor = "yes" if floor_opts["not_first"] else None
    #  - last_floor = "yes" if floor_opts["only_last"] else ("no" if floor_opts["not_last"] else None)
    #  - floor_max = 6 or 10 or 17 or None
    advanced_data = {}

    if floor_opts.get("not_first"):
        advanced_data["is_not_first_floor"] = "yes"
    else:
        advanced_data["is_not_first_floor"] = None

    if floor_opts.get("only_last"):
        advanced_data["last_floor"] = "yes"
    elif floor_opts.get("not_last"):
        advanced_data["last_floor"] = "no"
    else:
        advanced_data["last_floor"] = None

    if floor_opts.get("floor_max_6"):
        advanced_data["floor_max"] = 6
    elif floor_opts.get("floor_max_10"):
        advanced_data["floor_max"] = 10
    elif floor_opts.get("floor_max_17"):
        advanced_data["floor_max"] = 17
    else:
        advanced_data["floor_max"] = None

    # Save to state
    await state.update_data(**advanced_data)

    # Return to advanced menu or summary
    await callback_query.message.answer("Зміни збережено.")
    # e.g. show advanced menu again
    # or show final summary

    # **Now** go back to the advanced options menu:
    await show_advanced_options(callback_query.message, state)

    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "unsubscribe", state="*")
async def unsubscribe_callback(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    # In DB, set user subscription inactive or remove user_filters
    # e.g.
    sql = "UPDATE users SET subscription_until = NOW() WHERE telegram_id = %s"
    execute_query(sql, [user_id])

    await callback_query.message.answer("Ви відписалися від розсилки оголошень.")
    await callback_query.answer()


