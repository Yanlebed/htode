# services/viber_service/app/handlers/basic_handlers.py

import logging
import asyncio
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage
from ..bot import viber, state_manager
from ..utils.message_utils import safe_send_message, safe_send_picture
from ..keyboards import (
    create_main_menu_keyboard,
    create_property_type_keyboard,
    create_city_keyboard,
    create_rooms_keyboard,
    create_price_keyboard,
    create_confirmation_keyboard,
    create_edit_parameters_keyboard
)
from common.db.models import (
    get_or_create_user,
    update_user_filter,
    start_free_subscription_of_user,
    get_subscription_data_for_user,
    get_subscription_until_for_user
)
from common.config import GEO_ID_MAPPING, get_key_by_value
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

# City list (same as in your Telegram bot)
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


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


async def handle_message(user_id, message):
    """Handle text messages from users asynchronously"""
    if not isinstance(message, TextMessage):
        # For now, we only handle text messages
        await safe_send_message(user_id, "Підтримуються тільки текстові повідомлення.")
        return

    text = message.text

    # Get user state from Redis
    user_data = await state_manager.get_state(user_id) or {"state": STATE_START}
    current_state = user_data.get("state", STATE_START)

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
    await safe_send_message(
        user_id,
        "Головне меню:",
        keyboard=create_main_menu_keyboard()
    )

    # Reset state to start
    await state_manager.update_state(user_id, {
        "state": STATE_START
    })


async def handle_property_type(user_id, text):
    """Handle property type selection asynchronously"""
    # Get user data from state
    user_data = await state_manager.get_state(user_id) or {}

    # Map action body to property type
    property_mapping = {
        "property_type_apartment": "apartment",
        "property_type_house": "house"
    }

    if text in property_mapping:
        property_type = property_mapping[text]
        # Update user state
        await state_manager.update_state(user_id, {
            "property_type": property_type,
            "state": STATE_WAITING_CITY
        })

        # Move to city selection
        await safe_send_message(
            user_id,
            "🏙️ Оберіть місто:",
            keyboard=create_city_keyboard(AVAILABLE_CITIES)
        )
    else:
        await safe_send_message(
            user_id,
            "Будь ласка, оберіть тип нерухомості:",
            keyboard=create_property_type_keyboard()
        )


async def handle_city(user_id, text):
    """Handle city selection asynchronously"""
    # Get user data from state
    user_data = await state_manager.get_state(user_id) or {}

    # Check if the text starts with "city_"
    if text.startswith("city_"):
        city_name = text.split("_", 1)[1].capitalize()

        if city_name.lower() in [city.lower() for city in AVAILABLE_CITIES]:
            # Store city in user data
            await state_manager.update_state(user_id, {
                "city": city_name,
                "state": STATE_WAITING_ROOMS
            })

            # Move to rooms selection
            await safe_send_message(
                user_id,
                "🛏️ Виберіть кількість кімнат (можна обрати декілька):",
                keyboard=create_rooms_keyboard()
            )
        else:
            await safe_send_message(
                user_id,
                "Будь ласка, оберіть місто зі списку.",
                keyboard=create_city_keyboard(AVAILABLE_CITIES)
            )
    else:
        await safe_send_message(
            user_id,
            "Будь ласка, оберіть місто зі списку.",
            keyboard=create_city_keyboard(AVAILABLE_CITIES)
        )


async def handle_rooms(user_id, text):
    """Handle rooms selection asynchronously"""
    # Get user data from state
    user_data = await state_manager.get_state(user_id) or {}

    if text == "rooms_done":
        if "rooms" not in user_data or not user_data["rooms"]:
            await safe_send_message(
                user_id,
                "Ви не обрали кількість кімнат.",
                keyboard=create_rooms_keyboard(user_data.get("rooms", []))
            )
            return

        # Move to price selection
        await state_manager.update_state(user_id, {
            "state": STATE_WAITING_PRICE
        })

        await safe_send_message(
            user_id,
            "💰 Виберіть діапазон цін (грн):",
            keyboard=create_price_keyboard(user_data.get("city", "Київ"))
        )

    elif text == "rooms_any":
        # User selected "Any number of rooms"
        await state_manager.update_state(user_id, {
            "rooms": None,
            "state": STATE_WAITING_PRICE
        })

        # Move to price selection
        await safe_send_message(
            user_id,
            "💰 Виберіть діапазон цін (грн):",
            keyboard=create_price_keyboard(user_data.get("city", "Київ"))
        )

    elif text.startswith("rooms_"):
        try:
            # Parse room number, e.g., "rooms_1" -> 1
            room_number = int(text.split("_")[1])

            # Initialize rooms list if not exists
            rooms = user_data.get("rooms", [])

            # Toggle room selection
            if room_number in rooms:
                rooms.remove(room_number)
            else:
                rooms.append(room_number)

            await state_manager.update_state(user_id, {
                "rooms": rooms
            })

            # Show updated room selection keyboard
            await safe_send_message(
                user_id,
                f"Вибрані кімнати: {', '.join(map(str, rooms))}",
                keyboard=create_rooms_keyboard(rooms)
            )
        except (IndexError, ValueError):
            await safe_send_message(
                user_id,
                "Виникла помилка при виборі кількості кімнат.",
                keyboard=create_rooms_keyboard(user_data.get("rooms", []))
            )
    else:
        await safe_send_message(
            user_id,
            "Невідома команда.",
            keyboard=create_rooms_keyboard(user_data.get("rooms", []))
        )


async def handle_price(user_id, text):
    """Handle price range selection asynchronously"""
    # Get user data from state
    user_data = await state_manager.get_state(user_id) or {}

    # Parse price range from callback data
    # Format: "price_min_max" or "price_min_any"
    if text.startswith("price_"):
        parts = text.split("_")
        if len(parts) >= 3:
            try:
                min_price = int(parts[1])
                max_price = None if parts[2] == "any" else int(parts[2])

                # Store price range
                await state_manager.update_state(user_id, {
                    "price_min": min_price,
                    "price_max": max_price,
                    "state": STATE_CONFIRMATION
                })

                # Format price range for display
                price_text = f"{min_price}+ грн." if not max_price else f"{min_price}–{max_price} грн."
                await safe_send_message(
                    user_id,
                    f"Ви обрали діапазон: {price_text}"
                )

                # Show confirmation
                await show_confirmation(user_id)
            except (ValueError, IndexError):
                await safe_send_message(
                    user_id,
                    "Невірний формат діапазону цін.",
                    keyboard=create_price_keyboard(user_data.get("city", "Київ"))
                )
        else:
            await safe_send_message(
                user_id,
                "Будь ласка, оберіть діапазон цін:",
                keyboard=create_price_keyboard(user_data.get("city", "Київ"))
            )
    else:
        await safe_send_message(
            user_id,
            "Будь ласка, оберіть діапазон цін:",
            keyboard=create_price_keyboard(user_data.get("city", "Київ"))
        )


async def show_confirmation(user_id):
    """Show subscription confirmation asynchronously"""
    # Get user data from state
    user_data = await state_manager.get_state(user_id) or {}
    await state_manager.update_state(user_id, {
        "state": STATE_CONFIRMATION
    })

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
    await safe_send_message(
        user_id,
        summary,
        keyboard=create_confirmation_keyboard()
    )


async def handle_confirmation(user_id, text):
    """Handle confirmation of search parameters asynchronously"""
    # Get user data from state
    user_data = await state_manager.get_state(user_id) or {}

    if text == "subscribe":
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

            # Fetch some initial ads to show to the user
            # This would typically be done with your existing fetch_ads_for_period function
            # But for Viber we'll keep it simple for now
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
                "Помилка при збереженні фільтрів. Спробуйте ще раз.",
                keyboard=create_main_menu_keyboard()
            )

    elif text == "edit_parameters":
        # Show parameter editing menu
        await state_manager.update_state(user_id, {
            "state": STATE_EDITING_PARAMETERS
        })

        await safe_send_message(
            user_id,
            "Оберіть параметр для редагування:",
            keyboard=create_edit_parameters_keyboard()
        )

    elif text == "advanced_search":
        # Show advanced search options
        # Implement this if you have advanced search in your Telegram bot
        await safe_send_message(
            user_id,
            "Розширений пошук поки не доступний в Viber.",
            keyboard=create_confirmation_keyboard()
        )

    else:
        await safe_send_message(
            user_id,
            "Невідома команда. Будь ласка, використовуйте кнопки нижче:",
            keyboard=create_confirmation_keyboard()
        )


async def handle_edit_parameters(user_id, text):
    """Handle editing of parameters asynchronously"""
    # Get user data from state
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

        await safe_send_message(
            user_id,
            "💰 Виберіть діапазон цін (грн):",
            keyboard=create_price_keyboard(user_data.get("city", "Київ"))
        )

    elif text == "cancel_edit":
        # Return to confirmation
        await state_manager.update_state(user_id, {
            "state": STATE_CONFIRMATION
        })

        await show_confirmation(user_id)

    else:
        await safe_send_message(
            user_id,
            "Невідома команда. Будь ласка, використовуйте кнопки нижче:",
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
    else:
        await safe_send_message(
            user_id,
            "Не розумію цю команду. Будь ласка, використовуйте меню нижче:",
            keyboard=create_main_menu_keyboard()
        )