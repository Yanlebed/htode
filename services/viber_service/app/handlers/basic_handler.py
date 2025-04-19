# services/viber_service/app/handlers/basic_handlers.py

import logging
from viberbot.api.messages import TextMessage, KeyboardMessage, PictureMessage
from ..bot import viber, user_states
from ..keyboards import (
    create_main_menu_keyboard,
    create_property_type_keyboard,
    create_city_keyboard,
    create_rooms_keyboard,
    create_price_keyboard,
    create_confirmation_keyboard
)
from common.db.models import get_or_create_user, update_user_filter
from common.config import GEO_ID_MAPPING, get_key_by_value

logger = logging.getLogger(__name__)

# Define states
STATE_START = "start"
STATE_WAITING_PROPERTY_TYPE = "waiting_property_type"
STATE_WAITING_CITY = "waiting_city"
STATE_WAITING_ROOMS = "waiting_rooms"
STATE_WAITING_PRICE = "waiting_price"
STATE_CONFIRMATION = "confirmation"

# City list (same as in your Telegram bot)
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


def handle_conversation_started(user_id, viber_request):
    """Handle conversation started event"""
    # Send welcome message with main menu
    viber.send_messages(user_id, [
        TextMessage(
            text="Привіт!👋 Я бот з пошуку оголошень.\n"
                 "Зі мною легко і швидко знайти квартиру, будинок або кімнату для оренди.\n"
                 "У тебе зараз активний безкоштовний період 7 днів.\n"
                 "Давайте налаштуємо твої параметри пошуку.\n"
                 "Обери те, що тебе цікавить:\n"
        ),
        KeyboardMessage(keyboard=create_property_type_keyboard())
    ])

    # Store user state
    user_states[user_id] = {
        "state": STATE_WAITING_PROPERTY_TYPE
    }

    # Create user in database
    viber_id = viber_request.user.id
    user_db_id = get_or_create_user(viber_id, messenger_type="viber")
    user_states[user_id]["user_db_id"] = user_db_id


def handle_subscribed(user_id):
    """Handle user subscription to bot"""
    viber.send_messages(user_id, [
        TextMessage(text="Дякую за підписку на бота!"),
        KeyboardMessage(keyboard=create_main_menu_keyboard())
    ])


def handle_message(user_id, message):
    """Handle text messages from users"""
    if not isinstance(message, TextMessage):
        # For now, we only handle text messages
        viber.send_messages(user_id, [TextMessage(text="Підтримуються тільки текстові повідомлення.")])
        return

    text = message.text

    # If user not in states dict, initialize
    if user_id not in user_states:
        user_states[user_id] = {"state": STATE_START}
        # Get or create user in database
        user_db_id = get_or_create_user(user_id, messenger_type="viber")
        user_states[user_id]["user_db_id"] = user_db_id

    # Get current state
    current_state = user_states[user_id].get("state", STATE_START)

    # Handle commands first
    if text == "/start":
        handle_start_command(user_id)
        return
    elif text == "/menu":
        handle_menu_command(user_id)
        return

    # Handle based on current state
    if current_state == STATE_START:
        handle_start_command(user_id)
    elif current_state == STATE_WAITING_PROPERTY_TYPE:
        handle_property_type(user_id, text)
    elif current_state == STATE_WAITING_CITY:
        handle_city(user_id, text)
    elif current_state == STATE_WAITING_ROOMS:
        handle_rooms(user_id, text)
    elif current_state == STATE_WAITING_PRICE:
        handle_price(user_id, text)
    elif current_state == STATE_CONFIRMATION:
        handle_confirmation(user_id, text)
    else:
        # Handle main menu options
        handle_menu_option(user_id, text)


def handle_start_command(user_id):
    """Handle /start command"""
    # Similar to handle_conversation_started
    viber.send_messages(user_id, [
        TextMessage(
            text="Привіт!👋 Я бот з пошуку оголошень.\n"
                 "Зі мною легко і швидко знайти квартиру, будинок або кімнату для оренди.\n"
                 "У тебе зараз активний безкоштовний період 7 днів.\n"
                 "Давайте налаштуємо твої параметри пошуку.\n"
                 "Обери те, що тебе цікавить:\n"
        ),
        KeyboardMessage(keyboard=create_property_type_keyboard())
    ])

    # Store user state
    user_states[user_id] = {
        "state": STATE_WAITING_PROPERTY_TYPE
    }

    # Create user in database if not exists
    user_db_id = get_or_create_user(user_id, messenger_type="viber")
    user_states[user_id]["user_db_id"] = user_db_id


def handle_menu_command(user_id):
    """Handle /menu command"""
    viber.send_messages(user_id, [
        TextMessage(text="Головне меню:"),
        KeyboardMessage(keyboard=create_main_menu_keyboard())
    ])


def handle_property_type(user_id, text):
    """Handle property type selection"""
    user_data = user_states.get(user_id, {})

    # Map action body to property type
    property_mapping = {
        "property_type_apartment": "apartment",
        "property_type_house": "house"
    }

    if text in property_mapping:
        property_type = property_mapping[text]
        # Update user state
        user_data["property_type"] = property_type
        user_states[user_id] = user_data

        # Move to city selection
        user_data["state"] = STATE_WAITING_CITY
        viber.send_messages(user_id, [
            TextMessage(text="🏙️ Оберіть місто:"),
            KeyboardMessage(keyboard=create_city_keyboard(AVAILABLE_CITIES))
        ])
    else:
        viber.send_messages(user_id, [
            TextMessage(text="Будь ласка, оберіть тип нерухомості:"),
            KeyboardMessage(keyboard=create_property_type_keyboard())
        ])


def handle_city(user_id, text):
    """Handle city selection"""
    user_data = user_states.get(user_id, {})

    # Check if the text starts with "city_"
    if text.startswith("city_"):
        city_name = text.split("_", 1)[1].capitalize()

        if city_name.lower() in [city.lower() for city in AVAILABLE_CITIES]:
            # Store city in user data
            user_data["city"] = city_name
            user_states[user_id] = user_data

            # Move to rooms selection
            user_data["state"] = STATE_WAITING_ROOMS
            viber.send_messages(user_id, [
                TextMessage(text="🛏️ Виберіть кількість кімнат (можна обрати декілька):"),
                KeyboardMessage(keyboard=create_rooms_keyboard())
            ])
        else:
            viber.send_messages(user_id, [
                TextMessage(text="Будь ласка, оберіть місто зі списку."),
                KeyboardMessage(keyboard=create_city_keyboard(AVAILABLE_CITIES))
            ])
    else:
        viber.send_messages(user_id, [
            TextMessage(text="Будь ласка, оберіть місто зі списку."),
            KeyboardMessage(keyboard=create_city_keyboard(AVAILABLE_CITIES))
        ])


def handle_rooms(user_id, text):
    """Handle rooms selection"""
    user_data = user_states.get(user_id, {})

    if text == "rooms_done":
        if "rooms" not in user_data or not user_data["rooms"]:
            viber.send_messages(user_id, [
                TextMessage(text="Ви не обрали кількість кімнат."),
                KeyboardMessage(keyboard=create_rooms_keyboard(user_data.get("rooms", [])))
            ])
            return

        # Move to price selection
        user_data["state"] = STATE_WAITING_PRICE
        viber.send_messages(user_id, [
            TextMessage(text="💰 Виберіть діапазон цін (грн):"),
            KeyboardMessage(keyboard=create_price_keyboard(user_data.get("city", "Київ")))
        ])

    elif text == "rooms_any":
        # User selected "Any number of rooms"
        user_data["rooms"] = None
        user_states[user_id] = user_data

        # Move to price selection
        user_data["state"] = STATE_WAITING_PRICE
        viber.send_messages(user_id, [
            TextMessage(text="💰 Виберіть діапазон цін (грн):"),
            KeyboardMessage(keyboard=create_price_keyboard(user_data.get("city", "Київ")))
        ])

    elif text.startswith("rooms_"):
        try:
            # Parse room number, e.g., "rooms_1" -> 1
            room_number = int(text.split("_")[1])

            # Initialize rooms list if not exists
            if "rooms" not in user_data:
                user_data["rooms"] = []

            # Toggle room selection
            if room_number in user_data["rooms"]:
                user_data["rooms"].remove(room_number)
            else:
                user_data["rooms"].append(room_number)

            user_states[user_id] = user_data

            # Show updated room selection keyboard
            viber.send_messages(user_id, [
                TextMessage(text=f"Вибрані кімнати: {', '.join(map(str, user_data['rooms']))}"),
                KeyboardMessage(keyboard=create_rooms_keyboard(user_data["rooms"]))
            ])
        except (IndexError, ValueError):
            viber.send_messages(user_id, [
                TextMessage(text="Виникла помилка при виборі кількості кімнат."),
                KeyboardMessage(keyboard=create_rooms_keyboard(user_data.get("rooms", [])))
            ])
    else:
        viber.send_messages(user_id, [
            TextMessage(text="Невідома команда."),
            KeyboardMessage(keyboard=create_rooms_keyboard(user_data.get("rooms", [])))
        ])


def handle_price(user_id, text):
    """Handle price range selection"""
    user_data = user_states.get(user_id, {})

    # Parse price range from callback data
    # Format: "price_min_max" or "price_min_any"
    if text.startswith("price_"):
        parts = text.split("_")
        if len(parts) >= 3:
            try:
                min_price = int(parts[1])
                max_price = None if parts[2] == "any" else int(parts[2])

                # Store price range
                user_data["price_min"] = min_price
                user_data["price_max"] = max_price
                user_states[user_id] = user_data

                # Format price range for display
                price_text = f"{min_price}+ грн." if not max_price else f"{min_price}–{max_price} грн."
                viber.send_messages(user_id, [
                    TextMessage(text=f"Ви обрали діапазон: {price_text}")
                ])

                # Show confirmation
                show_confirmation(user_id)
            except (ValueError, IndexError):
                viber.send_messages(user_id, [
                    TextMessage(text="Невірний формат діапазону цін."),
                    KeyboardMessage(keyboard=create_price_keyboard(user_data.get("city", "Київ")))
                ])
        else:
            viber.send_messages(user_id, [
                TextMessage(text="Будь ласка, оберіть діапазон цін:"),
                KeyboardMessage(keyboard=create_price_keyboard(user_data.get("city", "Київ")))
            ])
    else:
        viber.send_messages(user_id, [
            TextMessage(text="Будь ласка, оберіть діапазон цін:"),
            KeyboardMessage(keyboard=create_price_keyboard(user_data.get("city", "Київ")))
        ])


def show_confirmation(user_id):
    """Show subscription confirmation"""
    user_data = user_states.get(user_id, {})
    user_data["state"] = STATE_CONFIRMATION
    user_states[user_id] = user_data

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
        f"**Обрані параметри пошуку:**\n"
        f"🏷 Тип нерухомості: {ua_lang_property_type}\n"
        f"🏙️ Місто: {city}\n"
        f"🛏️ Кількість кімнат: {rooms}\n"
        f"💰 Діапазон цін: {price_range} грн.\n"
    )

    # Send confirmation message
    viber.send_messages(user_id, [
        TextMessage(text=summary),
        KeyboardMessage(keyboard=create_confirmation_keyboard())
    ])


def handle_confirmation(user_id, text):
    """Handle confirmation of search parameters"""
    user_data = user_states.get(user_id, {})

    if text == "subscribe":
        # Get user database ID
        user_db_id = user_data.get("user_db_id")
        if not user_db_id:
            viber.send_messages(user_id, [
                TextMessage(text="Помилка: Не вдалося визначити вашого користувача.")
            ])
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
            from common.db.models import start_free_subscription_of_user
            start_free_subscription_of_user(user_db_id)

            # Send confirmation message
            viber.send_messages(user_id, [
                TextMessage(text="Ви успішно підписалися на пошук оголошень!")
            ])

            # Fetch some initial ads to show to the user
            # This would typically be done with your existing fetch_ads_for_period function
            # But for Viber we'll keep it simple for now
            viber.send_messages(user_id, [
                TextMessage(text="Ми будемо надсилати вам нові оголошення, щойно вони з'являтимуться!"),
                KeyboardMessage(keyboard=create_main_menu_keyboard())
            ])

            # Trigger ad notification task via Celery
            from common.celery_app import celery_app
            celery_app.send_task(
                'notifier_service.app.tasks.notify_user_with_ads',
                args=[user_db_id, filters]
            )

            # Reset state to main menu
            user_data["state"] = STATE_START
            user_states[user_id] = user_data

        except Exception as e:
            logger.error(f"Error updating user filters: {e}")
            viber.send_messages(user_id, [
                TextMessage(text="Помилка при збереженні фільтрів. Спробуйте ще раз."),
                KeyboardMessage(keyboard=create_main_menu_keyboard())
            ])

    elif text == "edit_parameters":
        # Show parameter editing menu
        viber.send_messages(user_id, [
            TextMessage(text="Оберіть параметр для редагування:"),
            KeyboardMessage(keyboard=create_edit_parameters_keyboard())
        ])

    elif text == "advanced_search":
        # Show advanced search options
        # Implement this if you have advanced search in your Telegram bot
        viber.send_messages(user_id, [
            TextMessage(text="Розширений пошук поки не доступний в Viber."),
            KeyboardMessage(keyboard=create_confirmation_keyboard())
        ])

    else:
        viber.send_messages(user_id, [
            TextMessage(text="Невідома команда. Будь ласка, використовуйте кнопки нижче:"),
            KeyboardMessage(keyboard=create_confirmation_keyboard())
        ])


def handle_menu_option(user_id, text):
    """Handle main menu option selection"""
    if text == "📝 Мої підписки":
        # This would call your subscription handlers
        # For now, just acknowledge
        viber.send_messages(user_id, [
            TextMessage(text="Функція перегляду підписок ще в розробці.")
        ])
    elif text == "❤️ Обрані":
        # This would show favorites
        viber.send_messages(user_id, [
            TextMessage(text="Функція перегляду обраних ще в розробці.")
        ])
    elif text == "🤔 Як це працює?":
        # Show help information
        viber.send_messages(user_id, [
            TextMessage(
                text="Як використовувати:\n\n"
                     "1. Налаштуйте параметри фільтра.\n"
                     "2. Увімкніть передплату.\n"
                     "3. Отримуйте сповіщення.\n\n"
                     "Якщо у вас є додаткові питання, зверніться до служби підтримки!"
            ),
            KeyboardMessage(keyboard=create_main_menu_keyboard())
        ])
    elif text == "💳 Оплатити підписку":
        # This would show payment options
        viber.send_messages(user_id, [
            TextMessage(text="Функція оплати підписки ще в розробці.")
        ])
    elif text == "🧑‍💻 Техпідтримка":
        # This would show support options
        viber.send_messages(user_id, [
            TextMessage(text="Функція техпідтримки ще в розробці.")
        ])
    else:
        viber.send_messages(user_id, [
            TextMessage(text="Не розумію цю команду. Будь ласка, використовуйте меню нижче:"),
            KeyboardMessage(keyboard=create_main_menu_keyboard())
        ])


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