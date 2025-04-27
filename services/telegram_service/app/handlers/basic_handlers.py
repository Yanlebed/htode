# services/telegram_service/app/handlers/basic_handlers.py

import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import ParseMode

from ..bot import dp
from ..states.basis_states import FilterStates
from ..keyboards import (
    property_type_keyboard, city_keyboard, rooms_keyboard,
    price_keyboard, confirmation_keyboard,
    edit_parameters_keyboard, floor_keyboard,
    main_menu_keyboard
)
from common.db.operations import get_or_create_user
from ..utils.message_utils import (
    safe_send_message, safe_answer_callback_query,
    safe_edit_message
)

logger = logging.getLogger(__name__)

# Список доступних міст (можна отримати з бази даних або конфігурації)
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


@dp.message_handler(commands=['start'])
async def start_command(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    user_db_id = get_or_create_user(telegram_id)  # Отримуємо внутрішній id користувача

    # Use safe_send_message instead of message.answer
    await safe_send_message(
        chat_id=telegram_id,
        text="Привіт!👋 Я бот з пошуку оголошень.\n"
             "Зі мною легко і швидко знайти квартиру, будинок або кімнату для оренди.\n"
             "У тебе зараз активний безкоштовний період 7 днів.\n"
             "Давайте налаштуємо твої параметри пошуку.\n"
             "Обери те, що тебе цікавить:\n",
        reply_markup=property_type_keyboard()
    )
    await FilterStates.waiting_for_property_type.set()

    # Сохраняем user_db_id в состоянии, чтобы использовать его позже
    await state.update_data(user_db_id=user_db_id, telegram_id=telegram_id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('property_type_'),
                           state=FilterStates.waiting_for_property_type)
async def process_property_type(callback_query: types.CallbackQuery, state: FSMContext):
    property_type = callback_query.data.split('_')[-1]
    await state.update_data(property_type=property_type)

    # Use safe_send_message
    await safe_send_message(
        chat_id=callback_query.from_user.id,
        text="🏙️ Оберіть місто:",
        reply_markup=city_keyboard(AVAILABLE_CITIES)
    )
    await FilterStates.waiting_for_city.set()

    # Use safe_answer_callback_query
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('city_'), state=FilterStates.waiting_for_city)
async def process_city(callback_query: types.CallbackQuery, state: FSMContext):
    city = callback_query.data.split('_', 1)[1].capitalize()
    if city not in AVAILABLE_CITIES:
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="Будь ласка, оберіть місто зі списку."
        )
        return
    await state.update_data(city=city)

    await safe_send_message(
        chat_id=callback_query.from_user.id,
        text="🛏️ Виберіть кількість кімнат (можна обрати декілька):",
        reply_markup=rooms_keyboard()
    )
    await FilterStates.waiting_for_rooms.set()
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('rooms_'), state=FilterStates.waiting_for_rooms)
async def process_rooms(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data
    user_data = await state.get_data()
    city = user_data.get('city')
    selected_rooms = user_data.get('rooms', [])

    if data == 'rooms_done':
        if not selected_rooms:
            await safe_send_message(
                chat_id=callback_query.from_user.id,
                text="Ви не обрали кількість кімнат."
            )
            return
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="💰 Виберіть діапазон цін (грн):",
            reply_markup=price_keyboard(city=city)
        )
        await FilterStates.waiting_for_price.set()
        await safe_answer_callback_query(callback_query.id)
    elif data == 'rooms_any':
        await state.update_data(rooms=None)
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="💰 Виберіть діапазон цін (грн):",
            reply_markup=price_keyboard(city=city)
        )
        await FilterStates.waiting_for_price.set()
        await safe_answer_callback_query(callback_query.id)
    elif data.startswith('rooms_'):
        try:
            rooms_number = int(data.split('_')[1])
            if rooms_number in selected_rooms:
                selected_rooms.remove(rooms_number)
            else:
                selected_rooms.append(rooms_number)
            await state.update_data(rooms=selected_rooms)

            # Use safe_edit_message_reply_markup instead
            await safe_edit_message(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=callback_query.message.text,
                reply_markup=rooms_keyboard(selected_rooms)
            )
            await safe_answer_callback_query(callback_query.id)
        except (IndexError, ValueError):
            await safe_send_message(
                chat_id=callback_query.from_user.id,
                text="Виникла помилка при виборі кількості кімнат."
            )
            await safe_answer_callback_query(callback_query.id)
    else:
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="Невідома команда."
        )
        await safe_answer_callback_query(callback_query.id)


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
    await safe_send_message(
        chat_id=callback_query.from_user.id,
        text=f"Ви обрали діапазон: {text_range}"
    )

    await state.update_data(price_min=low, price_max=high)

    # Instead of waiting for a new button press, call the "process_basic_params"
    # function directly, so it shows the summary + confirmation buttons.
    await process_basic_params(callback_query, state)

    # Mark it done, so we are now in waiting_for_confirmation
    # (Inside process_basic_params you set waiting_for_confirmation,
    #  so no need to set it again here.)
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(Text(startswith="edit_"), state=FilterStates.waiting_for_confirmation)
async def handle_edit(callback_query: types.CallbackQuery, state: FSMContext):
    edit_field = callback_query.data.split('_', 1)[1]
    user_data = await state.get_data()
    city = user_data.get('city')

    if edit_field == "property_type":
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="🏷 Оберіть тип нерухомості:",
            reply_markup=property_type_keyboard()
        )
        await FilterStates.waiting_for_property_type.set()
    elif edit_field == "city":
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="🏙️ Оберіть місто:",
            reply_markup=city_keyboard(AVAILABLE_CITIES)
        )
        await FilterStates.waiting_for_city.set()
    elif edit_field == "rooms":
        user_data = await state.get_data()
        selected_rooms = user_data.get('rooms', [])
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="🛏️ Виберіть кількість кімнат (можна вибрати декілька):",
            reply_markup=rooms_keyboard(selected_rooms)
        )
        await FilterStates.waiting_for_rooms.set()
    elif edit_field == "price":
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="💰 Виберіть діапазон цін (грн):",
            reply_markup=price_keyboard(city=city)
        )
        await FilterStates.waiting_for_price.set()
    elif edit_field == "floor":
        # call your function to handle floor editing
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="🏢 Налаштуйте поверх:",
            reply_markup=floor_keyboard()
        )
        # optionally change state, etc.
    elif edit_field == "cancel_edit":
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="Редагування скасовано.",
            reply_markup=confirmation_keyboard()
        )
        await FilterStates.waiting_for_confirmation.set()
    else:
        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="Невідомий параметр редагування."
        )

    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('confirmation_'),
                           state=FilterStates.waiting_for_basic_params)
async def process_basic_params(callback_query: types.CallbackQuery, state: FSMContext):
    # Получение всех данных из состояния
    user_data = await state.get_data()
    property_type = user_data.get('property_type')
    mapping_property = {"apartment": "Квартира", "house": "Будинок"}
    ua_lang_property_type = mapping_property.get(property_type, "")

    city = user_data.get('city')
    rooms = ', '.join(map(str, user_data.get('rooms'))) if user_data.get('rooms') else 'Не важливо'

    # Определение диапазона цен
    price_min = user_data.get('price_min')
    price_max = user_data.get('price_max')
    if price_min and price_max:
        price_range = f"{price_min}-{price_max}"
    elif price_min and not price_max:
        price_range = f"Більше {price_min}"
    elif not price_min and price_max:
        price_range = f"До {price_max}"
    else:
        price_range = "Не важливо"

    summary = (
        f"**Обрані параметри пошуку:**\n"
        f"🏷 Тип нерухомості: {ua_lang_property_type}\n"
        f"🏙️ Місто: {city}\n"
        f"🛏️ Кількість кімнат: {rooms}\n"
        f"💰 Діапазон цін: {price_range} грн.\n"
    )

    # Екранування спеціальних символів у повідомленні Markdown
    from aiogram.utils.markdown import escape_md
    summary_escaped = escape_md(summary).replace('\\', '')

    await safe_send_message(
        chat_id=callback_query.from_user.id,
        text=summary_escaped,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=confirmation_keyboard()
    )
    await FilterStates.waiting_for_confirmation.set()
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(Text(startswith="edit_parameters"), state=FilterStates.waiting_for_confirmation)
async def edit_parameters(callback_query: types.CallbackQuery, state: FSMContext):
    await safe_send_message(
        chat_id=callback_query.from_user.id,
        text="Оберіть параметр для редагування:",
        reply_markup=edit_parameters_keyboard()
    )
    await safe_answer_callback_query(callback_query.id)


@dp.message_handler(lambda message: True, content_types=['text'], state=None)
async def debug_all_messages(message: types.Message):
    """Debug handler that logs all text messages when not in any state"""
    logger.info(f"Received message: {message.text} from user {message.from_user.id}")

    # If the message is /start, try to respond directly
    if message.text == '/start':
        try:
            await message.answer("Debug response: Bot received your /start command. Trying to respond.")
            # Also try to invoke the regular handler programmatically
            await start_command(message)
        except Exception as e:
            logger.error(f"Error handling /start in debug handler: {e}")
            await message.answer(f"Error in start command: {str(e)}")
    elif message.text == '/menu':
        await show_main_menu(message)
    elif message.text == "📱 Додати номер телефону":
        from .phone_verification import start_phone_verification
        await start_phone_verification(message, FSMContext)


@dp.message_handler(commands=['menu'])
async def show_main_menu(message: types.Message):
    """
    Sends the main menu keyboard when the user uses /menu.
    """
    await safe_send_message(
        chat_id=message.chat.id,
        text="Головне меню:",
        reply_markup=main_menu_keyboard()
    )