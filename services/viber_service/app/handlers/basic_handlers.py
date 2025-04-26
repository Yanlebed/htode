# services/viber_service/app/handlers/basic_handlers.py

import logging

from ..bot import state_manager
from ..utils.message_utils import safe_send_message
from viberbot.api.messages import TextMessage
from common.db.models import (
    get_or_create_user,
    update_user_filter,
    start_free_subscription_of_user
)
from common.celery_app import celery_app

logger = logging.getLogger(__name__)

# Define states
STATE_START = "start"
STATE_WAITING_PROPERTY_TYPE = "waiting_property_type"
STATE_WAITING_CITY = "waiting_city"
STATE_WAITING_ROOMS = "waiting_rooms"
STATE_WAITING_PRICE = "waiting_price"
STATE_CONFIRMATION = "confirmation"
STATE_EDITING_PARAMETERS = "editing_parameters"

from ..flow_integration import check_and_process_flow

# City list (same as in your Telegram bot)
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


async def handle_message(user_id, message):
    """Handle text messages from users asynchronously"""
    if not isinstance(message, TextMessage):
        # For now, we only handle text messages
        await safe_send_message(user_id, "Підтримуються тільки текстові повідомлення.")
        return

    text = message.text

    # ADDED: First check if a flow should handle this message
    if await check_and_process_flow(user_id, text):
        # Message was handled by a flow, no further processing needed
        return

    # Rest of the original function continues below
    # Get user state from Redis
    user_data = await state_manager.get_state(user_id) or {"state": STATE_START}
    current_state = user_data.get("state", STATE_START)

    # Handle phone verification states
    from .phone_verification import (
        STATE_WAITING_FOR_PHONE,
        STATE_WAITING_FOR_CODE,
        STATE_WAITING_FOR_CONFIRMATION,
        handle_phone_input,
        handle_verification_code,
        handle_merge_confirmation
    )

    # Check for verification flow states first
    if current_state == STATE_WAITING_FOR_PHONE:
        await handle_phone_input(user_id, text)
        return
    elif current_state == STATE_WAITING_FOR_CODE:
        await handle_verification_code(user_id, text)
        return
    elif current_state == STATE_WAITING_FOR_CONFIRMATION:
        await handle_merge_confirmation(user_id, text)
        return

    # If no state or new user, create user_db_id
    if "user_db_id" not in user_data:
        user_db_id = get_or_create_user(user_id, messenger_type="viber")
        await state_manager.update_state(user_id, {
            "user_db_id": user_db_id
        })

    # Handle commands first
    if text == "/start":
        await handle_start_command(user_id)
        return
    elif text == "/menu":
        await handle_menu_command(user_id)
        return

    # Handle based on current state
    if current_state == STATE_START:
        await handle_start_command(user_id)
    elif current_state == STATE_WAITING_PROPERTY_TYPE:
        await handle_property_type(user_id, text)
    elif current_state == STATE_WAITING_CITY:
        await handle_city(user_id, text)
    elif current_state == STATE_WAITING_ROOMS:
        await handle_rooms(user_id, text)
    elif current_state == STATE_WAITING_PRICE:
        await handle_price(user_id, text)
    elif current_state == STATE_CONFIRMATION:
        await handle_confirmation(user_id, text)
    elif current_state == STATE_EDITING_PARAMETERS:
        await handle_edit_parameters(user_id, text)
    else:
        # Handle main menu options
        await handle_menu_option(user_id, text)


async def handle_conversation_started(user_id, viber_request):
    """Handle conversation started event asynchronously"""
    # Send welcome message with main menu
    await safe_send_message(
        user_id,
        "Привіт!👋 Я бот з пошуку оголошень.\n"
        "Зі мною легко і швидко знайти квартиру, будинок або кімнату для оренди.\n"
        "У тебе зараз активний безкоштовний період 7 днів.\n"
        "Давайте налаштуємо твої параметри пошуку.\n"
        "Обери те, що тебе цікавить:\n",
        keyboard=create_property_type_keyboard()
    )

    # Store user state in Redis
    await state_manager.set_state(user_id, {
        "state": STATE_WAITING_PROPERTY_TYPE
    })

    # Create user in database
    viber_id = viber_request.user.id
    user_db_id = get_or_create_user(viber_id, messenger_type="viber")
    await state_manager.update_state(user_id, {
        "user_db_id": user_db_id
    })


async def handle_subscribed(user_id):
    """Handle user subscription to bot asynchronously"""
    await safe_send_message(
        user_id,
        "Дякую за підписку на бота!",
        keyboard=create_main_menu_keyboard()
    )


async def handle_start_command(user_id):
    """Handle /start command asynchronously"""
    await safe_send_message(
        user_id,
        "Привіт!👋 Я бот з пошуку оголошень.\n"
        "Зі мною легко і швидко знайти квартиру, будинок або кімнату для оренди.\n"
        "У тебе зараз активний безкоштовний період 7 днів.\n"
        "Давайте налаштуємо твої параметри пошуку.\n"
        "Обери те, що тебе цікавить:\n",
        keyboard=create_property_type_keyboard()
    )

    # Store user state in Redis
    await state_manager.set_state(user_id, {
        "state": STATE_WAITING_PROPERTY_TYPE
    })

    # Create user in database if not exists
    user_db_id = get_or_create_user(user_id, messenger_type="viber")
    await state_manager.update_state(user_id, {
        "user_db_id": user_db_id
    })


async def handle_menu_command(user_id):
    """Handle /menu command asynchronously"""
    menu_text = "Головне меню:"

    # Reset state to start
    await state_manager.update_state(user_id, {
        "state": STATE_START
    })

    await safe_send_message(
        user_id,
        menu_text,
        keyboard=create_main_menu_keyboard()
    )


def create_property_type_keyboard():
    """Create keyboard for property type selection"""
    return {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Квартира",
                "ActionType": "reply",
                "ActionBody": "apartment"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Будинок",
                "ActionType": "reply",
                "ActionBody": "house"
            }
        ]
    }


def create_main_menu_keyboard():
    """Create main menu keyboard"""
    return {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "📝 Мої підписки",
                "ActionType": "reply",
                "ActionBody": "📝 Мої підписки"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "❤️ Обрані",
                "ActionType": "reply",
                "ActionBody": "❤️ Обрані"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "🤔 Як це працює?",
                "ActionType": "reply",
                "ActionBody": "🤔 Як це працює?"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "💳 Оплатити підписку",
                "ActionType": "reply",
                "ActionBody": "💳 Оплатити підписку"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "🧑‍💻 Техпідтримка",
                "ActionType": "reply",
                "ActionBody": "🧑‍💻 Техпідтримка"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "📱 Номер телефону",
                "ActionType": "reply",
                "ActionBody": "📱 Номер телефону"
            }
        ]
    }


async def handle_property_type(user_id, text):
    """Handle property type selection asynchronously"""
    property_mapping = {
        "apartment": "apartment",
        "house": "house",
        "квартира": "apartment",
        "будинок": "house"
    }

    text_lower = text.lower().strip()
    if text_lower in property_mapping:
        property_type = property_mapping[text_lower]
        # Update user state
        await state_manager.update_state(user_id, {
            "property_type": property_type,
            "state": STATE_WAITING_CITY
        })

        # Create city keyboard
        keyboard = create_city_keyboard(AVAILABLE_CITIES)

        # Move to city selection
        await safe_send_message(
            user_id,
            "🏙️ Оберіть місто:",
            keyboard=keyboard
        )
    else:
        await safe_send_message(
            user_id,
            "Будь ласка, оберіть тип нерухомості:",
            keyboard=create_property_type_keyboard()
        )


def create_city_keyboard(cities):
    """Create keyboard for city selection"""
    buttons = []

    # Create buttons for cities
    for city in cities:
        buttons.append({
            "Columns": 3,
            "Rows": 1,
            "Text": city,
            "ActionType": "reply",
            "ActionBody": f"city_{city.lower()}"
        })

    return {
        "Type": "keyboard",
        "ButtonsGroupColumns": 6,
        "ButtonsGroupRows": 7,
        "Buttons": buttons
    }


async def handle_city(user_id, text):
    """Handle city selection asynchronously"""
    # Check if input starts with "city_"
    if text.startswith("city_"):
        city_name = text.split("_", 1)[1].capitalize()

        # Check if city is in available cities list
        if city_name.lower() in [city.lower() for city in AVAILABLE_CITIES]:
            # Get city with proper capitalization
            for city in AVAILABLE_CITIES:
                if city.lower() == city_name.lower():
                    city_name = city
                    break

            # Update state with city
            await state_manager.update_state(user_id, {
                "city": city_name,
                "state": STATE_WAITING_ROOMS
            })

            # Move to rooms selection
            keyboard = create_rooms_keyboard()
            await safe_send_message(
                user_id,
                "🛏️ Виберіть кількість кімнат (можна обрати декілька):",
                keyboard=keyboard
            )
        else:
            await safe_send_message(
                user_id,
                "Місто не знайдено. Будь ласка, оберіть місто зі списку.",
                keyboard=create_city_keyboard(AVAILABLE_CITIES)
            )
    else:
        # Try to match city name without prefix
        for city in AVAILABLE_CITIES:
            if city.lower() == text.lower():
                await state_manager.update_state(user_id, {
                    "city": city,
                    "state": STATE_WAITING_ROOMS
                })

                # Move to rooms selection
                keyboard = create_rooms_keyboard()
                await safe_send_message(
                    user_id,
                    "🛏️ Виберіть кількість кімнат (можна обрати декілька):",
                    keyboard=keyboard
                )
                return

        # No match found
        await safe_send_message(
            user_id,
            "Будь ласка, оберіть місто зі списку.",
            keyboard=create_city_keyboard(AVAILABLE_CITIES)
        )


def create_rooms_keyboard(selected_rooms=None):
    """Create keyboard for room selection"""
    if selected_rooms is None:
        selected_rooms = []

    buttons = []

    # Add number buttons 1-5
    for room in range(1, 6):
        text = f"✅ {room}" if room in selected_rooms else f"{room}"
        buttons.append({
            "Columns": 1,
            "Rows": 1,
            "Text": text,
            "ActionType": "reply",
            "ActionBody": f"room_{room}"
        })

    # Add Done and Any buttons
    buttons.append({
        "Columns": 3,
        "Rows": 1,
        "Text": "Далі",
        "ActionType": "reply",
        "ActionBody": "rooms_done"
    })

    buttons.append({
        "Columns": 3,
        "Rows": 1,
        "Text": "Пропустити",
        "ActionType": "reply",
        "ActionBody": "rooms_any"
    })

    return {
        "Type": "keyboard",
        "ButtonsGroupColumns": 6,
        "ButtonsGroupRows": 2,
        "Buttons": buttons
    }


async def handle_rooms(user_id, text):
    """Handle rooms selection asynchronously"""
    user_data = await state_manager.get_state(user_id) or {}
    selected_rooms = user_data.get("rooms", [])

    if text == "rooms_done":
        if not selected_rooms:
            await safe_send_message(
                user_id,
                "Ви не обрали кількість кімнат."
            )
            return

        # Move to price selection
        city = user_data.get("city", "Київ")
        await state_manager.update_state(user_id, {
            "state": STATE_WAITING_PRICE
        })
        await show_price_options(user_id, city)
    elif text == "rooms_any":
        # User selected "Any number of rooms"
        await state_manager.update_state(user_id, {
            "rooms": None,
            "state": STATE_WAITING_PRICE
        })

        # Move to price selection
        city = user_data.get("city", "Київ")
        await show_price_options(user_id, city)
    elif text.startswith("room_"):
        try:
            room_number = int(text.split("_")[1])

            # Toggle room selection
            if room_number in selected_rooms:
                selected_rooms.remove(room_number)
            else:
                selected_rooms.append(room_number)

            # Update state with selected rooms
            await state_manager.update_state(user_id, {
                "rooms": selected_rooms
            })

            # Show updated keyboard
            keyboard = create_rooms_keyboard(selected_rooms)
            await safe_send_message(
                user_id,
                f"Обрані кімнати: {', '.join(map(str, selected_rooms))}",
                keyboard=keyboard
            )
        except (ValueError, IndexError):
            await safe_send_message(
                user_id,
                "Виникла помилка при виборі кількості кімнат."
            )
    else:
        # Try to parse room numbers from text
        try:
            # Parse room numbers, support both comma and space separated values
            parts = text.replace(",", " ").split()
            room_numbers = [int(part) for part in parts if part.isdigit() and 1 <= int(part) <= 5]

            if not room_numbers:
                raise ValueError("No valid room numbers found")

            # Update selected rooms
            await state_manager.update_state(user_id, {
                "rooms": room_numbers
            })

            # Show confirmation and keyboard
            keyboard = create_rooms_keyboard(room_numbers)
            await safe_send_message(
                user_id,
                f"Обрані кімнати: {', '.join(map(str, room_numbers))}",
                keyboard=keyboard
            )
        except ValueError:
            await safe_send_message(
                user_id,
                "Невірний формат вибору кімнат. Використовуйте кнопки або введіть числа через кому.",
                keyboard=create_rooms_keyboard(selected_rooms)
            )


async def show_price_options(user_id, city):
    """Show price range options based on city asynchronously"""
    # Get price ranges for the city
    price_ranges = await get_price_ranges(city)

    # Create keyboard with price range options
    keyboard = create_price_keyboard(price_ranges)

    await safe_send_message(
        user_id,
        "💰 Виберіть діапазон цін (грн):",
        keyboard=keyboard
    )


async def get_price_ranges(city):
    """Get price ranges for a city"""
    # Group cities by size for price ranges
    big_cities = {'Київ'}
    medium_cities = {'Харків', 'Дніпро', 'Одеса', 'Львів'}

    if city in big_cities:
        # up to 15000, 15000–20000, 20000–30000, more than 30000
        return [(0, 15000), (15000, 20000), (20000, 30000), (30000, None)]
    elif city in medium_cities:
        # up to 7000, 7000–10000, 10000–15000, more than 15000
        return [(0, 7000), (7000, 10000), (10000, 15000), (15000, None)]
    else:
        # Default to "smaller" city intervals
        # up to 5000, 5000–7000, 7000–10000, more than 10000
        return [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]


def create_price_keyboard(price_ranges):
    """Create keyboard for price range selection"""
    buttons = []

    for i, (low, high) in enumerate(price_ranges):
        if high is None:
            label = f"Більше {low} грн."
            callback = f"price_{low}_any"
        else:
            if low == 0:
                label = f"До {high} грн."
            else:
                label = f"{low}-{high} грн."
            callback = f"price_{low}_{high}"

        buttons.append({
            "Columns": 3,
            "Rows": 1,
            "Text": label,
            "ActionType": "reply",
            "ActionBody": callback
        })

    return {
        "Type": "keyboard",
        "ButtonsGroupColumns": 6,
        "ButtonsGroupRows": 2,
        "Buttons": buttons
    }


async def handle_price(user_id, text):
    """Handle price range selection asynchronously"""
    user_data = await state_manager.get_state(user_id) or {}

    if text.startswith("price_"):
        parts = text.split("_")

        try:
            low = int(parts[1])
            high = None if parts[2] == "any" else int(parts[2])

            # Update state with price range
            await state_manager.update_state(user_id, {
                "price_min": low if low > 0 else None,
                "price_max": high,
                "state": STATE_CONFIRMATION
            })

            # Format price range for display
            if high is None:
                price_text = f"Більше {low} грн."
            else:
                if low == 0:
                    price_text = f"До {high} грн."
                else:
                    price_text = f"{low}-{high} грн."

            # Show confirmation message
            await safe_send_message(
                user_id,
                f"Ви обрали діапазон: {price_text}"
            )

            # Show summary and confirmation
            await show_confirmation(user_id)
        except (ValueError, IndexError):
            await safe_send_message(
                user_id,
                "Невірний формат діапазону цін.",
                keyboard=create_price_keyboard(await get_price_ranges(user_data.get("city", "Київ")))
            )
    else:
        # Try to parse price range from text
        await safe_send_message(
            user_id,
            "Будь ласка, оберіть діапазон цін за допомогою кнопок.",
            keyboard=create_price_keyboard(await get_price_ranges(user_data.get("city", "Київ")))
        )


async def show_confirmation(user_id):
    """Show subscription confirmation asynchronously"""
    user_data = await state_manager.get_state(user_id) or {}

    # Build summary text
    property_type = user_data.get("property_type", "")
    city = user_data.get("city", "")
    rooms = ", ".join(map(str, user_data.get("rooms", []))) if user_data.get("rooms") else "Не важливо"

    price_min = user_data.get("price_min")
    price_max = user_data.get("price_max")
    if price_min and price_max:
        price_range = f"{price_min}-{price_max}"
    elif price_min and not price_max:
        price_range = f"Більше {price_min}"
    elif not price_min and price_max:
        price_range = f"До {price_max}"
    else:
        price_range = "Не важливо"

    # Property type human-readable
    mapping_property = {"apartment": "Квартира", "house": "Будинок"}
    ua_lang_property_type = mapping_property.get(property_type, "")

    summary = (
        "*Обрані параметри пошуку:*\n\n"
        f"🏷 Тип нерухомості: {ua_lang_property_type}\n"
        f"🏙️ Місто: {city}\n"
        f"🛏️ Кількість кімнат: {rooms}\n"
        f"💰 Діапазон цін: {price_range} грн.\n"
    )

    # Create confirmation keyboard
    keyboard = create_confirmation_keyboard()

    await safe_send_message(
        user_id,
        summary,
        keyboard=keyboard
    )


def create_confirmation_keyboard():
    """Create keyboard for subscription confirmation"""
    return {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Розширений пошук",
                "ActionType": "reply",
                "ActionBody": "advanced_search"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Редагувати",
                "ActionType": "reply",
                "ActionBody": "edit_parameters"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Підписатися",
                "ActionType": "reply",
                "ActionBody": "subscribe"
            }
        ]
    }


async def handle_confirmation(user_id, text):
    """Handle confirmation of search parameters asynchronously"""
    user_data = await state_manager.get_state(user_id) or {}
    text_lower = text.lower()

    if text_lower == "subscribe" or text_lower == "підписатися":
        # Get user database ID
        user_db_id = user_data.get("user_db_id")
        if not user_db_id:
            await safe_send_message(
                user_id,
                "Помилка: Не вдалося визначити вашого користувача."
            )
            return

        # Prepare filters for database
        filters = {
            'property_type': user_data.get('property_type'),
            'city': user_data.get('city'),
            'rooms': user_data.get('rooms'),
            'price_min': user_data.get('price_min'),
            'price_max': user_data.get('price_max'),
        }

        # Save filters to database
        try:
            update_user_filter(user_db_id, filters)
            start_free_subscription_of_user(user_db_id)

            # Send confirmation message
            await safe_send_message(
                user_id,
                "Ви успішно підписалися на пошук оголошень!"
            )

            # Send additional message about notifications
            await safe_send_message(
                user_id,
                "Ми будемо надсилати вам нові оголошення, щойно вони з'являтимуться!",
                keyboard=create_main_menu_keyboard()
            )

            # Trigger ad notification task via Celery
            celery_app.send_task(
                'notifier_service.app.tasks.notify_user_with_ads',
                args=[user_db_id, filters]
            )

            # Reset state to main menu
            await state_manager.update_state(user_id, {
                "state": STATE_START
            })
        except Exception as e:
            logger.error(f"Error updating user filters: {e}")
            await safe_send_message(
                user_id,
                "Помилка при збереженні фільтрів. Спробуйте ще раз."
            )
    elif text_lower == "edit_parameters" or text_lower == "редагувати":
        # Show parameter editing menu
        await state_manager.update_state(user_id, {
            "state": STATE_EDITING_PARAMETERS
        })

        keyboard = create_edit_parameters_keyboard()
        await safe_send_message(
            user_id,
            "Оберіть параметр для редагування:",
            keyboard=keyboard
        )
    elif text_lower == "advanced_search" or text_lower == "розширений пошук":
        await safe_send_message(
            user_id,
            "Розширений пошук поки не доступний в Viber."
        )
    else:
        await safe_send_message(
            user_id,
            "Невідома команда. Будь ласка, оберіть один з варіантів:",
            keyboard=create_confirmation_keyboard()
        )


def create_edit_parameters_keyboard():
    """Create keyboard for parameter editing"""
    return {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Тип нерухомості",
                "ActionType": "reply",
                "ActionBody": "edit_property_type"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Місто",
                "ActionType": "reply",
                "ActionBody": "edit_city"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Кількість кімнат",
                "ActionType": "reply",
                "ActionBody": "edit_rooms"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Діапазон цін",
                "ActionType": "reply",
                "ActionBody": "edit_price"
            },
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Відмінити",
                "ActionType": "reply",
                "ActionBody": "cancel_edit"
            }
        ]
    }


async def handle_edit_parameters(user_id, text):
    """Handle editing parameters asynchronously"""
    user_data = await state_manager.get_state(user_id) or {}

    if text == "edit_property_type":
        # Reset state to property type selection
        await state_manager.update_state(user_id, {
            "state": STATE_WAITING_PROPERTY_TYPE
        })

        await safe_send_message(
            user_id,
            "🏷 Оберіть тип нерухомості:",
            keyboard=create_property_type_keyboard()
        )
    elif text == "edit_city":
        # Reset state to city selection
        await state_manager.update_state(user_id, {
            "state": STATE_WAITING_CITY
        })

        await safe_send_message(
            user_id,
            "🏙️ Оберіть місто:",
            keyboard=create_city_keyboard(AVAILABLE_CITIES)
        )
    elif text == "edit_rooms":
        # Reset state to rooms selection
        await state_manager.update_state(user_id, {
            "state": STATE_WAITING_ROOMS
        })

        await safe_send_message(
            user_id,
            "🛏️ Виберіть кількість кімнат (можна обрати декілька):",
            keyboard=create_rooms_keyboard(user_data.get("rooms", []))
        )
    elif text == "edit_price":
        # Reset state to price selection
        await state_manager.update_state(user_id, {
            "state": STATE_WAITING_PRICE
        })

        city = user_data.get("city", "Київ")
        await show_price_options(user_id, city)
    elif text == "cancel_edit":
        # Return to confirmation
        await state_manager.update_state(user_id, {
            "state": STATE_CONFIRMATION
        })

        await show_confirmation(user_id)
    else:
        await safe_send_message(
            user_id,
            "Невідомий параметр редагування.",
            keyboard=create_edit_parameters_keyboard()
        )


async def handle_menu_option(user_id, text):
    """Handle main menu option selection asynchronously"""
    if text == "📝 Мої підписки":
        # This would call your subscription handlers
        # For now, just acknowledge
        await safe_send_message(
            user_id,
            "Функція перегляду підписок ще в розробці."
        )
    elif text == "❤️ Обрані":
        # This would show favorites
        await safe_send_message(
            user_id,
            "Функція перегляду обраних ще в розробці."
        )
    elif text == "🤔 Як це працює?":
        # Show help information
        await safe_send_message(
            user_id,
            "Як використовувати:\n\n"
            "1. Налаштуйте параметри фільтра.\n"
            "2. Увімкніть передплату.\n"
            "3. Отримуйте сповіщення.\n\n"
            "Якщо у вас є додаткові питання, зверніться до служби підтримки!",
            keyboard=create_main_menu_keyboard()
        )
    elif text == "💳 Оплатити підписку":
        # This would show payment options
        await safe_send_message(
            user_id,
            "Функція оплати підписки ще в розробці."
        )
    elif text == "🧑‍💻 Техпідтримка":
        # This would show support options
        await safe_send_message(
            user_id,
            "Функція техпідтримки ще в розробці."
        )
    elif text == "📱 Номер телефону" or text == "верифікація":
        # Start phone verification
        from .phone_verification import start_phone_verification
        await start_phone_verification(user_id)
    else:
        await safe_send_message(
            user_id,
            "Не розумію цю команду. Будь ласка, використовуйте меню нижче:",
            keyboard=create_main_menu_keyboard()
        )