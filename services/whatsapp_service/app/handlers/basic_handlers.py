# services/whatsapp_service/app/handlers/basic_handlers.py

import asyncio
from ..bot import state_manager
from ..utils.message_utils import safe_send_message
from common.db.operations import (
    get_or_create_user,
    update_user_filter,
    start_free_subscription_of_user
)
from common.celery_app import celery_app
from common.utils.logging_config import log_context, log_operation, LogAggregator

# Import the service logger
from .. import logger

# UPDATED: Add import for flow handling
from ..flow_integration import check_and_process_flow, process_numeric_flow_action, process_flow_action

# Define states
STATE_START = "start"
STATE_WAITING_PROPERTY_TYPE = "waiting_property_type"
STATE_WAITING_CITY = "waiting_city"
STATE_WAITING_ROOMS = "waiting_rooms"
STATE_WAITING_PRICE = "waiting_price"
STATE_CONFIRMATION = "confirmation"
STATE_EDITING_PARAMETERS = "editing_parameters"

# City list
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


@log_operation("handle_message")
async def handle_message(user_id, text, media_urls=None, response=None):
    """
    Handle incoming WhatsApp messages asynchronously

    Args:
        user_id: User's WhatsApp number (cleaned)
        text: Message text
        media_urls: List of media URLs from the message (if any)
        response: Twilio MessagingResponse object for immediate response
    """
    with log_context(logger, user_id=user_id, message_length=len(text), has_media=bool(media_urls)):
        logger.info(f"Processing message from {user_id}", extra={
            'text_preview': text[:50],
            'media_count': len(media_urls) if media_urls else 0
        })

        # ADDED: First check if a flow should handle this message
        if await check_and_process_flow(user_id, text, response):
            logger.info(f"Message handled by flow for user {user_id}")
            return

        # ADDED: Check for flow actions (for handling menu selection by number)
        user_data = await state_manager.get_state(user_id) or {"state": STATE_START}
        if text.isdigit() and await process_numeric_flow_action(user_id, text, user_data):
            logger.info(f"Numeric flow action processed for user {user_id}")
            return

        # ADDED: Check for explicit flow commands
        if text.startswith("flow:") and await process_flow_action(user_id, text):
            logger.info(f"Flow command processed for user {user_id}")
            return

        # Continue with regular message handling
        current_state = user_data.get("state", STATE_START)
        logger.debug(f"Current state for user {user_id}: {current_state}")

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
            logger.info(f"Handling phone input for user {user_id}")
            await handle_phone_input(user_id, text, response)
            return
        elif current_state == STATE_WAITING_FOR_CODE:
            logger.info(f"Handling verification code for user {user_id}")
            await handle_verification_code(user_id, text, response)
            return
        elif current_state == STATE_WAITING_FOR_CONFIRMATION:
            logger.info(f"Handling merge confirmation for user {user_id}")
            await handle_merge_confirmation(user_id, text, response)
            return

        # If no state or new user, create user_db_id
        if "user_db_id" not in user_data:
            with log_context(logger, operation="create_user"):
                user_db_id = get_or_create_user(user_id, messenger_type="whatsapp")
                await state_manager.update_state(user_id, {
                    "user_db_id": user_db_id
                })
                logger.info(f"Created database user ID {user_db_id} for WhatsApp user {user_id}")

        # Handle commands first
        if text.lower() == "/start":
            await handle_start_command(user_id, response)
            return
        elif text.lower() == "/menu":
            await handle_menu_command(user_id, response)
            return

        # Handle based on current state
        if current_state == STATE_START:
            await handle_start_command(user_id, response)
        elif current_state == STATE_WAITING_PROPERTY_TYPE:
            await handle_property_type(user_id, text, response)
        elif current_state == STATE_WAITING_CITY:
            await handle_city(user_id, text, response)
        elif current_state == STATE_WAITING_ROOMS:
            await handle_rooms(user_id, text, response)
        elif current_state == STATE_WAITING_PRICE:
            await handle_price(user_id, text, response)
        elif current_state == STATE_CONFIRMATION:
            await handle_confirmation(user_id, text, response)
        elif current_state == STATE_EDITING_PARAMETERS:
            await handle_edit_parameters(user_id, text, response)
        else:
            # Handle main menu options
            await handle_menu_option(user_id, text, response)


@log_operation("handle_start_command")
async def handle_start_command(user_id, response=None):
    """Handle /start command asynchronously"""
    with log_context(logger, user_id=user_id):
        logger.info(f"Processing /start command for user {user_id}")

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
            await safe_send_message(user_id, welcome_message)

        # Store user state in Redis
        await state_manager.set_state(user_id, {
            "state": STATE_WAITING_PROPERTY_TYPE
        })

        # Create user in database if not exists
        user_db_id = get_or_create_user(user_id, messenger_type="whatsapp")
        await state_manager.update_state(user_id, {
            "user_db_id": user_db_id
        })

        logger.info(f"Start command completed for user {user_id}")


@log_operation("handle_menu_command")
async def handle_menu_command(user_id, response=None):
    """Handle /menu command asynchronously"""
    with log_context(logger, user_id=user_id):
        logger.info(f"Processing /menu command for user {user_id}")

        menu_text = (
            "Головне меню:\n\n"
            "1. 📝 Мої підписки\n"
            "2. ❤️ Обрані\n"
            "3. 🤔 Як це працює?\n"
            "4. 💳 Оплатити підписку\n"
            "5. 🧑‍💻 Техпідтримка\n"
            "6. 📱 Номер телефону\n\n"
            "Введіть номер опції"
        )

        # Reset state to start
        await state_manager.update_state(user_id, {
            "state": STATE_START
        })

        if response:
            response.message(menu_text)
        else:
            await safe_send_message(user_id, menu_text)

        logger.info(f"Menu command completed for user {user_id}")


@log_operation("handle_property_type")
async def handle_property_type(user_id, text, response=None):
    """Handle property type selection asynchronously"""
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing property type selection for user {user_id}")

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
            logger.info(f"User {user_id} selected property type: {property_type}")

            # Update user state
            await state_manager.update_state(user_id, {
                "property_type": property_type,
                "state": STATE_WAITING_CITY
            })

            # Move to city selection
            city_options = "\n".join([f"{i + 1}. {city}" for i, city in enumerate(AVAILABLE_CITIES[:10])])
            city_message = (
                "🏙️ Оберіть місто (введіть номер або назву):\n\n"
                f"{city_options}\n\n"
                "Якщо вашого міста немає в списку, введіть його назву"
            )

            if response:
                response.message(city_message)
            else:
                await safe_send_message(user_id, city_message)
        else:
            logger.warning(f"Invalid property type input from user {user_id}: {text}")
            error_message = (
                "Будь ласка, оберіть тип нерухомості (введіть цифру):\n"
                "1. Квартира\n"
                "2. Будинок"
            )

            if response:
                response.message(error_message)
            else:
                await safe_send_message(user_id, error_message)


@log_operation("handle_city")
async def handle_city(user_id, text, response=None):
    """Handle city selection asynchronously"""
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing city selection for user {user_id}")

        # Get user data from state
        user_data = await state_manager.get_state(user_id) or {}
        text = text.strip()

        # Check if input is a number
        try:
            city_index = int(text) - 1
            if 0 <= city_index < len(AVAILABLE_CITIES):
                selected_city = AVAILABLE_CITIES[city_index]
                logger.info(f"User {user_id} selected city by index: {selected_city}")
            else:
                raise ValueError("City index out of range")
        except ValueError:
            # Try to match text with city name
            text_lower = text.lower()
            matching_cities = [city for city in AVAILABLE_CITIES if city.lower() == text_lower]

            if matching_cities:
                selected_city = matching_cities[0]
                logger.info(f"User {user_id} selected city by name: {selected_city}")
            else:
                logger.warning(f"Invalid city input from user {user_id}: {text}")
                city_options = "\n".join([f"{i + 1}. {city}" for i, city in enumerate(AVAILABLE_CITIES[:10])])
                error_message = (
                    "Місто не знайдено. Будь ласка, оберіть зі списку (введіть номер або назву):\n\n"
                    f"{city_options}"
                )

                if response:
                    response.message(error_message)
                else:
                    await safe_send_message(user_id, error_message)
                return

        # Store city in user data
        await state_manager.update_state(user_id, {
            "city": selected_city,
            "state": STATE_WAITING_ROOMS
        })

        # Move to rooms selection
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
            await safe_send_message(user_id, rooms_message)


@log_operation("handle_rooms")
async def handle_rooms(user_id, text, response=None):
    """Handle rooms selection asynchronously"""
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing rooms selection for user {user_id}")

        # Get user data from state
        user_data = await state_manager.get_state(user_id) or {}
        text = text.strip()

        if text == "6" or text.lower() in ["будь-яка", "будь яка", "будь-яка кількість кімнат"]:
            logger.info(f"User {user_id} selected 'Any number of rooms'")
            # User selected "Any number of rooms"
            await state_manager.update_state(user_id, {
                "rooms": None,
                "state": STATE_WAITING_PRICE
            })

            # Move to price selection
            await show_price_options(user_id, user_data.get("city", "Київ"), response)
        else:
            try:
                # Parse room numbers, support both comma and space separated values
                parts = text.replace(",", " ").split()
                room_numbers = [int(part) for part in parts if part.isdigit() and 1 <= int(part) <= 5]

                if not room_numbers:
                    raise ValueError("No valid room numbers found")

                logger.info(f"User {user_id} selected rooms: {room_numbers}")

                # Store selected rooms
                await state_manager.update_state(user_id, {
                    "rooms": room_numbers,
                    "state": STATE_WAITING_PRICE
                })

                # Show confirmation and move to price selection
                rooms_text = ", ".join(map(str, room_numbers))
                confirm_message = f"Обрано кімнат: {rooms_text}"

                if response:
                    response.message(confirm_message)
                    # Don't use the same response twice
                    await asyncio.sleep(0.5)  # Small delay before the next message
                    await show_price_options(user_id, user_data.get("city", "Київ"), None)
                else:
                    await safe_send_message(user_id, confirm_message)
                    await show_price_options(user_id, user_data.get("city", "Київ"), None)
            except ValueError:
                logger.warning(f"Invalid rooms input from user {user_id}: {text}")
                error_message = (
                    "Невірний формат. Будь ласка, введіть цифри від 1 до 5, розділені комами або пробілами.\n"
                    "Наприклад: 1,2,3 або 2 3 4\n"
                    "Або введіть 6 для будь-якої кількості кімнат."
                )

                if response:
                    response.message(error_message)
                else:
                    await safe_send_message(user_id, error_message)


@log_operation("get_price_ranges")
async def get_price_ranges(city):
    """
    Returns price ranges for the given city asynchronously.
    """
    with log_context(logger, city=city):
        # Group cities by size for price ranges
        big_cities = {'Київ'}
        medium_cities = {'Харків', 'Дніпро', 'Одеса', 'Львів'}

        if city in big_cities:
            ranges = [(0, 15000), (15000, 20000), (20000, 30000), (30000, None)]
        elif city in medium_cities:
            ranges = [(0, 7000), (7000, 10000), (10000, 15000), (15000, None)]
        else:
            ranges = [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]

        logger.debug(f"Price ranges for {city}: {ranges}")
        return ranges


@log_operation("show_price_options")
async def show_price_options(user_id, city, response=None):
    """Show price range options based on city asynchronously"""
    with log_context(logger, user_id=user_id, city=city):
        logger.info(f"Showing price options for city {city} to user {user_id}")

        price_ranges = await get_price_ranges(city)

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
            await safe_send_message(user_id, price_message)


@log_operation("handle_price")
async def handle_price(user_id, text, response=None):
    """Handle price range selection asynchronously"""
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing price selection for user {user_id}")

        # Get user data from state
        user_data = await state_manager.get_state(user_id) or {}
        text = text.strip()

        city = user_data.get("city", "Київ")
        price_ranges = await get_price_ranges(city)

        try:
            selection = int(text)
            if 1 <= selection <= len(price_ranges):
                low, high = price_ranges[selection - 1]
                logger.info(f"User {user_id} selected price range: {low}-{high}")

                # Store price range
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

                confirm_message = f"Ви обрали діапазон: {price_text}"

                if response:
                    response.message(confirm_message)
                    # Don't use the same response twice
                    await asyncio.sleep(0.5)  # Small delay before showing confirmation
                    await show_confirmation(user_id, None)
                else:
                    await safe_send_message(user_id, confirm_message)
                    await show_confirmation(user_id, None)
            else:
                raise ValueError("Selection out of range")
        except (ValueError, IndexError):
            logger.warning(f"Invalid price selection from user {user_id}: {text}")
            error_message = (
                "Будь ласка, оберіть діапазон цін, ввівши цифру від 1 до "
                f"{len(price_ranges)}."
            )

            if response:
                response.message(error_message)
            else:
                await safe_send_message(user_id, error_message)


@log_operation("show_confirmation")
async def show_confirmation(user_id, response=None):
    """Show subscription confirmation asynchronously"""
    with log_context(logger, user_id=user_id):
        logger.info(f"Showing confirmation to user {user_id}")

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
            await safe_send_message(user_id, summary)


@log_operation("handle_confirmation")
async def handle_confirmation(user_id, text, response=None):
    """Handle confirmation of search parameters asynchronously"""
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing confirmation for user {user_id}")

        # Get user data from state
        user_data = await state_manager.get_state(user_id) or {}
        text_lower = text.lower().strip()

        if text_lower in ["підписатися", "subscribe", "1"]:
            # Get user database ID
            user_db_id = user_data.get("user_db_id")
            if not user_db_id:
                logger.error(f"No user_db_id found for user {user_id}")
                error_message = "Помилка: Не вдалося визначити вашого користувача."
                if response:
                    response.message(error_message)
                else:
                    await safe_send_message(user_id, error_message)
                return

            # Prepare filters for database
            filters = {
                'property_type': user_data.get('property_type'),
                'city': user_data.get('city'),
                'rooms': user_data.get('rooms'),
                'price_min': user_data.get('price_min'),
                'price_max': user_data.get('price_max'),
            }

            logger.info(f"Saving filters for user {user_id}: {filters}")

            # Save filters to database
            try:
                update_user_filter(user_db_id, filters)
                start_free_subscription_of_user(user_db_id)

                # Send confirmation message
                success_message = "Ви успішно підписалися на пошук оголошень!"
                if response:
                    response.message(success_message)
                else:
                    await safe_send_message(user_id, success_message)

                # Send additional message about notifications
                notification_message = "Ми будемо надсилати вам нові оголошення, щойно вони з'являтимуться!"
                await safe_send_message(user_id, notification_message)

                # Trigger ad notification task via Celery
                celery_app.send_task(
                    'notifier_service.app.tasks.notify_user_with_ads',
                    args=[user_db_id, filters]
                )

                # Reset state to main menu
                await state_manager.update_state(user_id, {
                    "state": STATE_START
                })

                # Show main menu
                await handle_menu_command(user_id, None)

                logger.info(f"Successfully created subscription for user {user_id}")

            except Exception as e:
                logger.error(f"Error updating user filters", exc_info=True, extra={
                    'user_id': user_id,
                    'user_db_id': user_db_id,
                    'error_type': type(e).__name__
                })
                error_message = "Помилка при збереженні фільтрів. Спробуйте ще раз."
                if response:
                    response.message(error_message)
                else:
                    await safe_send_message(user_id, error_message)

        elif text_lower in ["редагувати", "edit", "2"]:
            logger.info(f"User {user_id} chose to edit parameters")
            # Update state to editing parameters
            await state_manager.update_state(user_id, {
                "state": STATE_EDITING_PARAMETERS
            })

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
                await safe_send_message(user_id, edit_message)

        elif text_lower in ["розширений", "advanced", "3"]:
            logger.info(f"User {user_id} requested advanced search (not available)")
            advanced_message = "Розширений пошук поки не доступний в WhatsApp."

            if response:
                response.message(advanced_message)
            else:
                await safe_send_message(user_id, advanced_message)

        else:
            logger.warning(f"Invalid confirmation input from user {user_id}: {text}")
            error_message = (
                "Будь ласка, введіть:\n"
                "'Підписатися' - щоб підтвердити параметри\n"
                "'Редагувати' - щоб змінити параметри\n"
                "'Розширений' - для розширеного пошуку"
            )

            if response:
                response.message(error_message)
            else:
                await safe_send_message(user_id, error_message)


@log_operation("handle_edit_parameters")
async def handle_edit_parameters(user_id, text, response=None):
    """Handle editing parameters asynchronously"""
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing edit parameters for user {user_id}")

        # Get user data from state
        user_data = await state_manager.get_state(user_id) or {}
        text = text.strip()

        try:
            option = int(text)
            logger.debug(f"User {user_id} selected edit option {option}")

            if option == 1:  # Edit property type
                await state_manager.update_state(user_id, {
                    "state": STATE_WAITING_PROPERTY_TYPE
                })

                message = (
                    "Обери тип нерухомості (введи цифру):\n"
                    "1. Квартира\n"
                    "2. Будинок"
                )

                if response:
                    response.message(message)
                else:
                    await safe_send_message(user_id, message)

            elif option == 2:  # Edit city
                await state_manager.update_state(user_id, {
                    "state": STATE_WAITING_CITY
                })

                city_options = "\n".join([f"{i + 1}. {city}" for i, city in enumerate(AVAILABLE_CITIES[:10])])
                message = (
                    "🏙️ Оберіть місто (введіть номер або назву):\n\n"
                    f"{city_options}\n\n"
                    "Якщо вашого міста немає в списку, введіть його назву"
                )

                if response:
                    response.message(message)
                else:
                    await safe_send_message(user_id, message)

            elif option == 3:  # Edit rooms
                await state_manager.update_state(user_id, {
                    "state": STATE_WAITING_ROOMS
                })

                message = (
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
                    response.message(message)
                else:
                    await safe_send_message(user_id, message)

            elif option == 4:  # Edit price
                await state_manager.update_state(user_id, {
                    "state": STATE_WAITING_PRICE
                })

                await show_price_options(user_id, user_data.get("city", "Київ"), response)

            elif option == 5:  # Cancel editing
                await state_manager.update_state(user_id, {
                    "state": STATE_CONFIRMATION
                })

                await show_confirmation(user_id, response)

            else:
                raise ValueError("Invalid option")

        except (ValueError, TypeError):
            logger.warning(f"Invalid edit option from user {user_id}: {text}")
            message = (
                "Невірний формат. Будь ласка, введіть цифру від 1 до 5:\n\n"
                "1. Тип нерухомості\n"
                "2. Місто\n"
                "3. Кількість кімнат\n"
                "4. Діапазон цін\n"
                "5. Скасувати редагування"
            )

            if response:
                response.message(message)
            else:
                await safe_send_message(user_id, message)


@log_operation("handle_menu_option")
async def handle_menu_option(user_id, text, response=None):
    # TODO: finish async def handle_menu_option
    """Handle main menu option selection asynchronously"""
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing menu option for user {user_id}")
        text_lower = text.lower().strip()

        # Handle both text and numeric input
        if text_lower in ["1", "мої підписки", "📝 мої підписки"]:
            logger.info(f"User {user_id} selected subscriptions")
            # Subscription management
            message = "Функція перегляду підписок ще в розробці."
            if response:
                response.message(message)
            else:
                await safe_send_message(user_id, message)

        elif text_lower in ["2", "обрані", "❤️ обрані"]:
            logger.info(f"User {user_id} selected favorites")
            # Favorites
            message = "Функція перегляду обраних ще в розробці."
            if response:
                response.message(message)
            else:
                await safe_send_message(user_id, message)

        elif text_lower in ["3", "як це працює", "🤔 як це працює"]:
            logger.info(f"User {user_id} selected how it works")
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
                await safe_send_message(user_id, help_message)

        elif text_lower in ["4", "оплатити підписку", "💳 оплатити підписку"]:
            logger.info(f"User {user_id} selected payment")
            # Payment
            message = "Функція оплати підписки ще в розробці."
            if response:
                response.message(message)
            else:
                await safe_send_message(user_id, message)

        elif text_lower in ["5", "🧑‍💻 техпідтримка", "техпідтримка", "🧑‍💻 техпідтримка"]:
            logger.info(f"User {user_id} selected support")
            # Support
            support_message = (
                "Для зв'язку з техпідтримкою, будь ласка, опишіть вашу проблему.\n"
                "Почніть повідомлення з 'Підтримка:' і ми відповімо якнайшвидше."
            )
            if response:
                response.message(support_message)
            else:
                await safe_send_message(user_id, support_message)

        elif text_lower in ["📱 номер телефону", "номер телефону", "верифікація"]:
            logger.info(f"User {user_id} selected phone verification")
            # Phone verification
            from .phone_verification import start_phone_verification
            await start_phone_verification(user_id, response)

        else:
            # Check if this is a support request
            if text_lower.startswith("підтримка:") or text_lower.startswith("support:"):
                support_request = text[text.find(":") + 1:].strip()
                if support_request:
                    logger.info(f"Support request from {user_id}: {support_request}")

                    # Forward to support system or notify admins (implementation depends on your setup)
                    thank_you_message = "Дякуємо за звернення. Наша команда підтримки зв'яжеться з вами найближчим часом."
                    if response:
                        response.message(thank_you_message)
                    else:
                        await safe_send_message(user_id, thank_you_message)
                    return

            logger.warning(f"Unknown menu option from user {user_id}: {text}")

            # Parse ad-related commands (format: "фото 123", "тел 123", etc.)
            command_parts = text.lower().split()
            if len(command_parts) == 2:
                command, ad_id_str = command_parts
                # ... (rest of the original logic)