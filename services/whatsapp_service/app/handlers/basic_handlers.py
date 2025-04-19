# services/whatsapp_service/app/handlers/basic_handlers.py

import logging
from ..bot import send_message, user_states
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

# City list
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


def handle_message(user_id, text, media_urls=None, response=None):
    """
    Handle incoming WhatsApp messages

    Args:
        user_id: User's WhatsApp number (cleaned)
        text: Message text
        media_urls: List of media URLs from the message (if any)
        response: Twilio MessagingResponse object for immediate response
    """
    # If user not in states dict, initialize
    if user_id not in user_states:
        user_states[user_id] = {"state": STATE_START}
        # Get or create user in database
        user_db_id = get_or_create_user(user_id, messenger_type="whatsapp")
        user_states[user_id]["user_db_id"] = user_db_id

    # Get current state
    current_state = user_states[user_id].get("state", STATE_START)

    # Handle commands first
    if text.lower() == "/start":
        handle_start_command(user_id, response)
        return
    elif text.lower() == "/menu":
        handle_menu_command(user_id, response)
        return

    # Handle based on current state
    if current_state == STATE_START:
        handle_start_command(user_id, response)
    elif current_state == STATE_WAITING_PROPERTY_TYPE:
        handle_property_type(user_id, text, response)
    elif current_state == STATE_WAITING_CITY:
        handle_city(user_id, text, response)
    elif current_state == STATE_WAITING_ROOMS:
        handle_rooms(user_id, text, response)
    elif current_state == STATE_WAITING_PRICE:
        handle_price(user_id, text, response)
    elif current_state == STATE_CONFIRMATION:
        handle_confirmation(user_id, text, response)
    else:
        # Handle main menu options
        handle_menu_option(user_id, text, response)


def handle_start_command(user_id, response=None):
    """Handle /start command"""
    welcome_message = (
        "Привіт!👋 Я бот з пошуку оголошень.\n"
        "Зі мною легко і швидко знайти квартиру, будинок або кімнату для оренди.\n"
        "У тебе зараз активний безкоштовний період 7 днів.\n"
        "Давайте налаштуємо твої параметри пошуку.\n\n"
        "Обери тип нерухомості (введи цифру):\n"
        "1. Квартира\n"
        "2. Будинок"
    )

    # Send response
    if response:
        response.message(welcome_message)
    else:
        send_message(user_id, welcome_message)

    # Store user state
    user_states[user_id] = {
        "state": STATE_WAITING_PROPERTY_TYPE
    }

    # Create user in database if not exists
    user_db_id = get_or_create_user(user_id, messenger_type="whatsapp")
    user_states[user_id]["user_db_id"] = user_db_id


def handle_menu_command(user_id, response=None):
    """Handle /menu command"""
    menu_text = (
        "Головне меню:\n\n"
        "1. 📝 Мої підписки\n"
        "2. ❤️ Обрані\n"
        "3. 🤔 Як це працює?\n"
        "4. 💳 Оплатити підписку\n"
        "5. 🧑‍💻 Техпідтримка\n\n"
        "Введіть номер опції"
    )

    if response:
        response.message(menu_text)
    else:
        send_message(user_id, menu_text)


def handle_property_type(user_id, text, response=None):
    """Handle property type selection"""
    user_data = user_states.get(user_id, {})

    # Map numeric input to property type
    property_mapping = {
        "1": "apartment",
        "квартира": "apartment",
        "2": "house",
        "будинок": "house"
    }

    text_lower = text.lower().strip()
    if text_lower in property_mapping:
        property_type = property_mapping[text_lower]
        # Update user state
        user_data["property_type"] = property_type
        user_states[user_id] = user_data

        # Move to city selection
        user_data["state"] = STATE_WAITING_CITY

        city_options = "\n".join([f"{i + 1}. {city}" for i, city in enumerate(AVAILABLE_CITIES[:10])])
        city_message = (
            "🏙️ Оберіть місто (введіть номер або назву):\n\n"
            f"{city_options}\n\n"
            "Якщо вашого міста немає в списку, введіть його назву"
        )

        if response:
            response.message(city_message)
        else:
            send_message(user_id, city_message)
    else:
        error_message = (
            "Будь ласка, оберіть тип нерухомості (введіть цифру):\n"
            "1. Квартира\n"
            "2. Будинок"
        )

        if response:
            response.message(error_message)
        else:
            send_message(user_id, error_message)


def handle_city(user_id, text, response=None):
    """Handle city selection"""
    user_data = user_states.get(user_id, {})
    text = text.strip()

    # Check if input is a number
    try:
        city_index = int(text) - 1
        if 0 <= city_index < len(AVAILABLE_CITIES):
            selected_city = AVAILABLE_CITIES[city_index]
        else:
            raise ValueError("City index out of range")
    except ValueError:
        # Try to match text with city name
        text_lower = text.lower()
        matching_cities = [city for city in AVAILABLE_CITIES if city.lower() == text_lower]

        if matching_cities:
            selected_city = matching_cities[0]
        else:
            city_options = "\n".join([f"{i + 1}. {city}" for i, city in enumerate(AVAILABLE_CITIES[:10])])
            error_message = (
                "Місто не знайдено. Будь ласка, оберіть зі списку (введіть номер або назву):\n\n"
                f"{city_options}"
            )

            if response:
                response.message(error_message)
            else:
                send_message(user_id, error_message)
            return

    # Store city in user data
    user_data["city"] = selected_city
    user_states[user_id] = user_data

    # Move to rooms selection
    user_data["state"] = STATE_WAITING_ROOMS
    rooms_message = (
        "🛏️ Виберіть кількість кімнат:\n\n"
        "1. 1 кімната\n"
        "2. 2 кімнати\n"
        "3. 3 кімнати\n"
        "4. 4 кімнати\n"
        "5. 5 кімнат\n"
        "6. Будь-яка кількість кімнат\n\n"
        "Ви можете вибрати кілька варіантів, розділивши їх комами, наприклад: 1,2,3"
    )

    if response:
        response.message(rooms_message)
    else:
        send_message(user_id, rooms_message)


def handle_rooms(user_id, text, response=None):
    """Handle rooms selection"""
    user_data = user_states.get(user_id, {})
    text = text.strip()

    if text == "6" or text.lower() in ["будь-яка", "будь яка", "будь-яка кількість кімнат"]:
        # User selected "Any number of rooms"
        user_data["rooms"] = None
        user_states[user_id] = user_data

        # Move to price selection
        user_data["state"] = STATE_WAITING_PRICE
        show_price_options(user_id, user_data.get("city", "Київ"), response)
    else:
        try:
            # Parse room numbers, support both comma and space separated values
            parts = text.replace(",", " ").split()
            room_numbers = [int(part) for part in parts if part.isdigit() and 1 <= int(part) <= 5]

            if not room_numbers:
                raise ValueError("No valid room numbers found")

            # Store selected rooms
            user_data["rooms"] = room_numbers
            user_states[user_id] = user_data

            # Show confirmation and move to price selection
            rooms_text = ", ".join(map(str, room_numbers))
            confirm_message = f"Обрано кімнат: {rooms_text}"

            if response:
                response.message(confirm_message)
            else:
                send_message(user_id, confirm_message)

            # Move to price selection
            user_data["state"] = STATE_WAITING_PRICE
            show_price_options(user_id, user_data.get("city", "Київ"), None)  # Don't use the same response twice
        except ValueError:
            error_message = (
                "Невірний формат. Будь ласка, введіть цифри від 1 до 5, розділені комами або пробілами.\n"
                "Наприклад: 1,2,3 або 2 3 4\n"
                "Або введіть 6 для будь-якої кількості кімнат."
            )

            if response:
                response.message(error_message)
            else:
                send_message(user_id, error_message)


def get_price_ranges(city):
    """
    Returns price ranges for the given city.
    """
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


def show_price_options(user_id, city, response=None):
    """Show price range options based on city"""
    price_ranges = get_price_ranges(city)

    options = []
    for i, (low, high) in enumerate(price_ranges):
        if high is None:
            options.append(f"{i + 1}. Більше {low} грн.")
        else:
            if low == 0:
                options.append(f"{i + 1}. До {high} грн.")
            else:
                options.append(f"{i + 1}. {low}-{high} грн.")

    price_message = (
            "💰 Виберіть діапазон цін (грн):\n\n"
            + "\n".join(options)
    )

    if response:
        response.message(price_message)
    else:
        send_message(user_id, price_message)


def handle_price(user_id, text, response=None):
    """Handle price range selection"""
    user_data = user_states.get(user_id, {})
    text = text.strip()

    city = user_data.get("city", "Київ")
    price_ranges = get_price_ranges(city)

    try:
        selection = int(text)
        if 1 <= selection <= len(price_ranges):
            low, high = price_ranges[selection - 1]

            # Store price range
            user_data["price_min"] = low if low > 0 else None
            user_data["price_max"] = high
            user_states[user_id] = user_data

            # Format price range for display
            if high is None:
                price_text = f"Більше {low} грн."
            else:
                if low == 0:
                    price_text = f"До {high} грн."
                else:
                    price_text = f"{low}-{high} грн."

            confirm_message = f"Ви обрали діапазон: {price_text}"

            if response:
                response.message(confirm_message)
            else:
                send_message(user_id, confirm_message)

            # Show confirmation
            show_confirmation(user_id, None)  # Don't use the same response twice
        else:
            raise ValueError("Selection out of range")
    except (ValueError, IndexError):
        error_message = (
            "Будь ласка, оберіть діапазон цін, ввівши цифру від 1 до "
            f"{len(price_ranges)}."
        )

        if response:
            response.message(error_message)
        else:
            send_message(user_id, error_message)


def show_confirmation(user_id, response=None):
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
        "*Обрані параметри пошуку:*\n\n"
        f"🏷 Тип нерухомості: {ua_lang_property_type}\n"
        f"🏙️ Місто: {city}\n"
        f"🛏️ Кількість кімнат: {rooms}\n"
        f"💰 Діапазон цін: {price_range} грн.\n\n"
        "Щоб підписатися, введіть 'Підписатися'.\n"
        "Щоб змінити параметри, введіть 'Редагувати'.\n"
        "Для розширеного пошуку введіть 'Розширений'."
    )

    if response:
        response.message(summary)
    else:
        send_message(user_id, summary)


def handle_confirmation(user_id, text, response=None):
    """Handle confirmation of search parameters"""
    user_data = user_states.get(user_id, {})
    text_lower = text.lower().strip()

    if text_lower in ["підписатися", "subscribe", "1"]:
        # Get user database ID
        user_db_id = user_data.get("user_db_id")
        if not user_db_id:
            error_message = "Помилка: Не вдалося визначити вашого користувача."
            if response:
                response.message(error_message)
            else:
                send_message(user_id, error_message)
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
            success_message = "Ви успішно підписалися на пошук оголошень!"
            if response:
                response.message(success_message)
            else:
                send_message(user_id, success_message)

            # Send additional message about notifications
            notification_message = "Ми будемо надсилати вам нові оголошення, щойно вони з'являтимуться!"
            send_message(user_id, notification_message)

            # Trigger ad notification task via Celery
            from common.celery_app import celery_app
            celery_app.send_task(
                'notifier_service.app.tasks.notify_user_with_ads',
                args=[user_db_id, filters]
            )

            # Reset state to main menu
            user_data["state"] = STATE_START
            user_states[user_id] = user_data

            # Show main menu
            handle_menu_command(user_id, None)

        except Exception as e:
            logger.error(f"Error updating user filters: {e}")
            error_message = "Помилка при збереженні фільтрів. Спробуйте ще раз."
            if response:
                response.message(error_message)
            else:
                send_message(user_id, error_message)

    elif text_lower in ["редагувати", "edit", "2"]:
        edit_message = (
            "Оберіть параметр для редагування (введіть цифру):\n\n"
            "1. Тип нерухомості\n"
            "2. Місто\n"
            "3. Кількість кімнат\n"
            "4. Діапазон цін\n"
            "5. Скасувати редагування"
        )

        if response:
            response.message(edit_message)
        else:
            send_message(user_id, edit_message)

    elif text_lower in ["розширений", "advanced", "3"]:
        advanced_message = "Розширений пошук поки не доступний в WhatsApp."

        if response:
            response.message(advanced_message)
        else:
            send_message(user_id, advanced_message)

    else:
        error_message = (
            "Будь ласка, введіть:\n"
            "'Підписатися' - щоб підтвердити параметри\n"
            "'Редагувати' - щоб змінити параметри\n"
            "'Розширений' - для розширеного пошуку"
        )

        if response:
            response.message(error_message)
        else:
            send_message(user_id, error_message)


def handle_menu_option(user_id, text, response=None):
    """Handle main menu option selection"""
    text_lower = text.lower().strip()

    # Handle both text and numeric input
    if text_lower in ["1", "мої підписки", "📝 мої підписки"]:
        # Subscription management
        message = "Функція перегляду підписок ще в розробці."
        if response:
            response.message(message)
        else:
            send_message(user_id, message)

    elif text_lower in ["2", "обрані", "❤️ обрані"]:
        # Favorites
        message = "Функція перегляду обраних ще в розробці."
        if response:
            response.message(message)
        else:
            send_message(user_id, message)

    elif text_lower in ["3", "як це працює", "🤔 як це працює"]:
        # Help information
        help_message = (
            "Як використовувати:\n\n"
            "1. Налаштуйте параметри фільтра.\n"
            "2. Увімкніть передплату.\n"
            "3. Отримуйте сповіщення.\n\n"
            "Якщо у вас є додаткові питання, зверніться до служби підтримки!"
        )
        if response:
            response.message(help_message)
        else:
            send_message(user_id, help_message)

    elif text_lower in ["4", "оплатити підписку", "💳 оплатити підписку"]:
        # Payment
        message = "Функція оплати підписки ще в розробці."
        if response:
            response.message(message)
        else:
            send_message(user_id, message)


    elif text_lower in ["5", "техпідтримка", "🧑‍💻 техпідтримка"]:
        # Support
        support_message = (
            "Для зв'язку з техпідтримкою, будь ласка, опишіть вашу проблему.\n"
            "Почніть повідомлення з 'Підтримка:' і ми відповімо якнайшвидше."
        )
        if response:
            response.message(support_message)
        else:
            send_message(user_id, support_message)

    else:
        # Check if this is a support request
        if text_lower.startswith("підтримка:") or text_lower.startswith("support:"):
            support_request = text[text.find(":") + 1:].strip()
            if support_request:
                # Log the support request
                logger.info(f"Support request from {user_id}: {support_request}")

                # Forward to support system or notify admins (implementation depends on your setup)
                thank_you_message = "Дякуємо за звернення. Наша команда підтримки зв'яжеться з вами найближчим часом."
                if response:
                    response.message(thank_you_message)
                else:
                    send_message(user_id, thank_you_message)
                return

        # Unknown command
        menu_message = (
            "Не розумію цю команду. Ось доступні опції:\n\n"
            "1. 📝 Мої підписки\n"
            "2. ❤️ Обрані\n"
            "3. 🤔 Як це працює?\n"
            "4. 💳 Оплатити підписку\n"
            "5. 🧑‍💻 Техпідтримка\n\n"
            "Введіть номер опції або /start щоб почати з початку."
        )
        if response:
            response.message(menu_message)
        else:
            send_message(user_id, menu_message)