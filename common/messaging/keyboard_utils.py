# common/messaging/keyboard_utils.py

from typing import List, Dict, Any
from common.utils.logging_config import log_operation, log_context

# Import the logger from the parent module
from . import logger

# City data for reference
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']

CITY_GROUPS = {
    'big_cities': {'Київ'},
    'medium_cities': {'Харків', 'Дніпро', 'Одеса', 'Львів'},
    'small_cities': set(AVAILABLE_CITIES) - {'Київ', 'Харків', 'Дніпро', 'Одеса', 'Львів'}
}


@log_operation("get_price_ranges")
def get_price_ranges(city: str) -> List[tuple]:
    """
    Returns price ranges for the given city.

    Args:
        city: City name

    Returns:
        List of (min_price, max_price) tuples
    """
    with log_context(logger, city=city):
        if city in CITY_GROUPS['big_cities']:
            # up to 15000, 15000–20000, 20000–30000, more than 30000
            ranges = [(0, 15000), (15000, 20000), (20000, 30000), (30000, None)]
        elif city in CITY_GROUPS['medium_cities']:
            # up to 7000, 7000–10000, 10000–15000, more than 15000
            ranges = [(0, 7000), (7000, 10000), (10000, 15000), (15000, None)]
        else:
            # Default to "smaller" city intervals
            # up to 5000, 5000–7000, 7000–10000, more than 10000
            ranges = [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]

        logger.debug("Got price ranges", extra={
            'city': city,
            'ranges_count': len(ranges),
            'city_group': 'big' if city in CITY_GROUPS['big_cities'] else
            'medium' if city in CITY_GROUPS['medium_cities'] else 'small'
        })

        return ranges


class KeyboardFactory:
    """
    Factory class for creating platform-specific keyboards with a unified interface.

    Provides methods to generate keyboards for various scenarios:
    - Main menu
    - Property type selection
    - City selection
    - Room selection
    - Price range selection
    - Subscription confirmation
    - Edit parameters
    """

    @staticmethod
    @log_operation("create_keyboard")
    def create_keyboard(platform: str, keyboard_type: str, **kwargs) -> Any:
        """
        Create a platform-specific keyboard.

        Args:
            platform: Platform name ('telegram', 'viber', 'whatsapp')
            keyboard_type: Type of keyboard to create
            **kwargs: Additional parameters for specific keyboard types

        Returns:
            Platform-specific keyboard object
        """
        with log_context(logger, platform=platform, keyboard_type=keyboard_type):
            try:
                if platform == "telegram":
                    result = TelegramKeyboardFactory.create_keyboard(keyboard_type, **kwargs)
                elif platform == "viber":
                    result = ViberKeyboardFactory.create_keyboard(keyboard_type, **kwargs)
                elif platform == "whatsapp":
                    result = WhatsAppKeyboardFactory.create_keyboard(keyboard_type, **kwargs)
                else:
                    logger.warning(f"Unsupported platform", extra={'platform': platform})
                    return None

                logger.debug("Keyboard created successfully", extra={
                    'platform': platform,
                    'keyboard_type': keyboard_type,
                    'has_result': bool(result)
                })

                return result
            except Exception as e:
                logger.error("Error creating keyboard", exc_info=True, extra={
                    'platform': platform,
                    'keyboard_type': keyboard_type,
                    'error_type': type(e).__name__
                })
                return None


class TelegramKeyboardFactory:
    """Factory for Telegram-specific keyboards"""

    @classmethod
    @log_operation("create_telegram_keyboard")
    def create_keyboard(cls, keyboard_type: str, **kwargs) -> Any:
        """Create a Telegram keyboard based on type"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

        with log_context(logger, keyboard_type=keyboard_type):
            if keyboard_type == "main_menu":
                return cls.create_main_menu_keyboard()
            elif keyboard_type == "property_type":
                return cls.create_property_type_keyboard()
            elif keyboard_type == "city":
                cities = kwargs.get('cities', AVAILABLE_CITIES)
                return cls.create_city_keyboard(cities)
            elif keyboard_type == "rooms":
                selected_rooms = kwargs.get('selected_rooms', [])
                return cls.create_rooms_keyboard(selected_rooms)
            elif keyboard_type == "price":
                city = kwargs.get('city', 'Київ')
                return cls.create_price_keyboard(city)
            elif keyboard_type == "confirmation":
                return cls.create_confirmation_keyboard()
            elif keyboard_type == "edit_parameters":
                return cls.create_edit_parameters_keyboard()
            elif keyboard_type == "floor":
                floor_opts = kwargs.get('floor_opts', None)
                return cls.create_floor_keyboard(floor_opts)
            else:
                logger.warning(f"Unknown keyboard type for Telegram", extra={'keyboard_type': keyboard_type})
                return None

    @staticmethod
    @log_operation("create_main_menu_keyboard")
    def create_main_menu_keyboard():
        """Create the main menu keyboard for Telegram"""
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row(
            KeyboardButton("📝 Мої підписки"),
            KeyboardButton("❤️ Обрані")
        )
        keyboard.row(
            KeyboardButton("🤔 Як це працює?"),
            KeyboardButton("💳 Оплатити підписку")
        )
        keyboard.row(
            KeyboardButton("🧑‍💻 Техпідтримка"),
            KeyboardButton("📱 Додати номер телефону")
        )

        logger.debug("Created Telegram main menu keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_property_type_keyboard")
    def create_property_type_keyboard():
        """Create keyboard for property type selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Квартира", callback_data="property_type_apartment"),
            InlineKeyboardButton("Будинок", callback_data="property_type_house")
        )

        logger.debug("Created Telegram property type keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_city_keyboard")
    def create_city_keyboard(cities):
        """Create keyboard for city selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        with log_context(logger, cities_count=len(cities)):
            keyboard = InlineKeyboardMarkup(row_width=2)
            for city in cities:
                keyboard.add(
                    InlineKeyboardButton(city, callback_data=f"city_{city.lower()}")
                )

            logger.debug("Created Telegram city keyboard", extra={'cities_count': len(cities)})
            return keyboard

    @staticmethod
    @log_operation("create_rooms_keyboard")
    def create_rooms_keyboard(selected_rooms=None):
        """Create keyboard for room selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        if selected_rooms is None:
            selected_rooms = []

        with log_context(logger, selected_rooms=selected_rooms):
            keyboard = InlineKeyboardMarkup(row_width=3)
            for rooms in range(1, 6):
                if rooms in selected_rooms:
                    button_text = f"✅ {rooms}"
                else:
                    button_text = str(rooms)
                keyboard.insert(
                    InlineKeyboardButton(button_text, callback_data=f"rooms_{rooms}")
                )
            keyboard.add(
                InlineKeyboardButton("Далі", callback_data="rooms_done"),
                InlineKeyboardButton("Пропустити", callback_data="rooms_any")
            )

            logger.debug("Created Telegram rooms keyboard", extra={'selected_count': len(selected_rooms)})
            return keyboard

    @staticmethod
    @log_operation("create_price_keyboard")
    def create_price_keyboard(city):
        """Create keyboard for price range selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        with log_context(logger, city=city):
            intervals = get_price_ranges(city)
            keyboard = InlineKeyboardMarkup(row_width=2)
            for (low, high) in intervals:
                if high is None:
                    label = f"Більше {low}"
                    callback_data = f"price_{low}_any"
                else:
                    # E.g. "0-5000 UAH", "5000-7000 UAH"
                    if low == 0:
                        label = f"До {high}"  # "up to X"
                    else:
                        label = f"{low}-{high}"
                    callback_data = f"price_{low}_{high}"

                keyboard.insert(
                    InlineKeyboardButton(label, callback_data=callback_data)
                )

            logger.debug("Created Telegram price keyboard", extra={
                'city': city,
                'intervals_count': len(intervals)
            })
            return keyboard

    @staticmethod
    @log_operation("create_confirmation_keyboard")
    def create_confirmation_keyboard():
        """Create keyboard for subscription confirmation"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Розширений пошук", callback_data="advanced_search"),
            InlineKeyboardButton("Редагувати", callback_data="edit_parameters"),
            InlineKeyboardButton("Підписатися", callback_data="subscribe")
        )

        logger.debug("Created Telegram confirmation keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_edit_parameters_keyboard")
    def create_edit_parameters_keyboard():
        """Create keyboard for parameter editing"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Тип нерухомості", callback_data="edit_property_type"),
            InlineKeyboardButton("Місто", callback_data="edit_city"),
            InlineKeyboardButton("Кількість кімнат", callback_data="edit_rooms"),
            InlineKeyboardButton("Діапазон цін", callback_data="edit_price"),
            InlineKeyboardButton("Поверх", callback_data="edit_floor"),
            InlineKeyboardButton("З тваринами?", callback_data="pets_allowed"),
            InlineKeyboardButton("Від власника?", callback_data="without_broker"),
            InlineKeyboardButton("Відмінити", callback_data="cancel_edit"),
        )

        logger.debug("Created Telegram edit parameters keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_floor_keyboard")
    def create_floor_keyboard(floor_opts=None):
        """Create keyboard for floor selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        if floor_opts is None:
            floor_opts = {
                "not_first": False,
                "not_last": False,
                "floor_max_6": False,
                "floor_max_10": False,
                "floor_max_17": False,
                "only_last": False
            }

        with log_context(logger, floor_opts=floor_opts):
            def mark(label, active):
                return f"{'✅ ' if active else ''}{label}"

            kb = InlineKeyboardMarkup(row_width=2)
            kb.insert(InlineKeyboardButton(
                mark("Не перший", floor_opts["not_first"]),
                callback_data="toggle_floor_not_first"
            ))
            kb.insert(InlineKeyboardButton(
                mark("Не останній", floor_opts["not_last"]),
                callback_data="toggle_floor_not_last"
            ))

            kb.add(InlineKeyboardButton(
                mark("До 6 поверху", floor_opts.get("floor_max_6", False)),
                callback_data="toggle_floor_6"
            ))
            kb.insert(InlineKeyboardButton(
                mark("До 10 поверху", floor_opts.get("floor_max_10", False)),
                callback_data="toggle_floor_10"
            ))
            kb.insert(InlineKeyboardButton(
                mark("До 17 поверху", floor_opts.get("floor_max_17", False)),
                callback_data="toggle_floor_17"
            ))

            kb.add(InlineKeyboardButton(
                mark("Останній", floor_opts.get("only_last", False)),
                callback_data="toggle_floor_only_last"
            ))

            # add "Back" or "Done" button
            kb.add(InlineKeyboardButton("Готово", callback_data="floor_done"))

            logger.debug("Created Telegram floor keyboard")
            return kb


class ViberKeyboardFactory:
    """Factory for Viber-specific keyboards"""

    @classmethod
    @log_operation("create_viber_keyboard")
    def create_keyboard(cls, keyboard_type: str, **kwargs) -> Dict[str, Any]:
        """Create a Viber keyboard based on type"""
        with log_context(logger, keyboard_type=keyboard_type):
            if keyboard_type == "main_menu":
                return cls.create_main_menu_keyboard()
            elif keyboard_type == "property_type":
                return cls.create_property_type_keyboard()
            elif keyboard_type == "city":
                cities = kwargs.get('cities', AVAILABLE_CITIES)
                return cls.create_city_keyboard(cities)
            elif keyboard_type == "rooms":
                selected_rooms = kwargs.get('selected_rooms', [])
                return cls.create_rooms_keyboard(selected_rooms)
            elif keyboard_type == "price":
                city = kwargs.get('city', 'Київ')
                return cls.create_price_keyboard(city)
            elif keyboard_type == "confirmation":
                return cls.create_confirmation_keyboard()
            elif keyboard_type == "edit_parameters":
                return cls.create_edit_parameters_keyboard()
            else:
                logger.warning(f"Unknown keyboard type for Viber", extra={'keyboard_type': keyboard_type})
                return {"Type": "keyboard", "Buttons": []}

    @staticmethod
    @log_operation("create_viber_main_menu_keyboard")
    def create_main_menu_keyboard():
        """Create the main menu keyboard for Viber"""
        keyboard = {
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
                    "Columns": 6,
                    "Rows": 1,
                    "Text": "🧑‍💻 Техпідтримка",
                    "ActionType": "reply",
                    "ActionBody": "🧑‍💻 Техпідтримка"
                }
            ]
        }

        logger.debug("Created Viber main menu keyboard", extra={'buttons_count': len(keyboard['Buttons'])})
        return keyboard

    @staticmethod
    @log_operation("create_viber_property_type_keyboard")
    def create_property_type_keyboard():
        """Create keyboard for property type selection"""
        keyboard = {
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

        logger.debug("Created Viber property type keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_viber_city_keyboard")
    def create_city_keyboard(cities):
        """Create keyboard for city selection"""
        with log_context(logger, cities_count=len(cities)):
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

            keyboard = {
                "Type": "keyboard",
                "ButtonsGroupColumns": 6,
                "ButtonsGroupRows": 7,
                "Buttons": buttons
            }

            logger.debug("Created Viber city keyboard", extra={'cities_count': len(cities)})
            return keyboard

    @staticmethod
    @log_operation("create_viber_rooms_keyboard")
    def create_rooms_keyboard(selected_rooms=None):
        """Create keyboard for room selection"""
        if selected_rooms is None:
            selected_rooms = []

        with log_context(logger, selected_rooms=selected_rooms):
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

            keyboard = {
                "Type": "keyboard",
                "ButtonsGroupColumns": 6,
                "ButtonsGroupRows": 2,
                "Buttons": buttons
            }

            logger.debug("Created Viber rooms keyboard", extra={'selected_count': len(selected_rooms)})
            return keyboard

    @staticmethod
    @log_operation("create_viber_price_keyboard")
    def create_price_keyboard(city):
        """Create keyboard for price range selection"""
        with log_context(logger, city=city):
            intervals = get_price_ranges(city)
            buttons = []

            for i, (low, high) in enumerate(intervals):
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

            keyboard = {
                "Type": "keyboard",
                "ButtonsGroupColumns": 6,
                "ButtonsGroupRows": 2,
                "Buttons": buttons
            }

            logger.debug("Created Viber price keyboard", extra={
                'city': city,
                'intervals_count': len(intervals)
            })
            return keyboard

    @staticmethod
    @log_operation("create_viber_confirmation_keyboard")
    def create_confirmation_keyboard():
        """Create keyboard for subscription confirmation"""
        keyboard = {
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

        logger.debug("Created Viber confirmation keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_viber_edit_parameters_keyboard")
    def create_edit_parameters_keyboard():
        """Create keyboard for parameter editing"""
        keyboard = {
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

        logger.debug("Created Viber edit parameters keyboard")
        return keyboard


class WhatsAppKeyboardFactory:
    """
    Factory for WhatsApp keyboards.

    Since WhatsApp doesn't support rich keyboards via the Twilio API,
    this class creates text-based menu strings.
    """

    @classmethod
    @log_operation("create_whatsapp_keyboard")
    def create_keyboard(cls, keyboard_type: str, **kwargs) -> str:
        """Create a WhatsApp text-based menu based on type"""
        with log_context(logger, keyboard_type=keyboard_type):
            if keyboard_type == "main_menu":
                return cls.create_main_menu_keyboard()
            elif keyboard_type == "property_type":
                return cls.create_property_type_keyboard()
            elif keyboard_type == "city":
                cities = kwargs.get('cities', AVAILABLE_CITIES)
                limit = kwargs.get('limit', 10)
                return cls.create_city_keyboard(cities, limit)
            elif keyboard_type == "rooms":
                selected_rooms = kwargs.get('selected_rooms', [])
                return cls.create_rooms_keyboard(selected_rooms)
            elif keyboard_type == "price":
                city = kwargs.get('city', 'Київ')
                return cls.create_price_keyboard(city)
            elif keyboard_type == "confirmation":
                return cls.create_confirmation_keyboard()
            elif keyboard_type == "edit_parameters":
                return cls.create_edit_parameters_keyboard()
            else:
                logger.warning(f"Unknown keyboard type for WhatsApp", extra={'keyboard_type': keyboard_type})
                return "Меню недоступне."

    @staticmethod
    @log_operation("create_whatsapp_main_menu_keyboard")
    def create_main_menu_keyboard():
        """Create the main menu text for WhatsApp"""
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

        logger.debug("Created WhatsApp main menu")
        return menu_text

    @staticmethod
    @log_operation("create_whatsapp_property_type_keyboard")
    def create_property_type_keyboard():
        """Create property type menu text for WhatsApp"""
        menu_text = (
            "Обери тип нерухомості (введи цифру):\n"
            "1. Квартира\n"
            "2. Будинок"
        )

        logger.debug("Created WhatsApp property type menu")
        return menu_text

    @staticmethod
    @log_operation("create_whatsapp_city_keyboard")
    def create_city_keyboard(cities, limit=10):
        """Create city selection menu text for WhatsApp"""
        with log_context(logger, cities_count=len(cities), limit=limit):
            city_list = cities[:limit]  # Limit to avoid too long messages
            city_options = "\n".join([f"{i + 1}. {city}" for i, city in enumerate(city_list)])

            menu_text = (
                "🏙️ Оберіть місто (введіть номер або назву):\n\n"
                f"{city_options}\n\n"
                "Якщо вашого міста немає в списку, введіть його назву"
            )

            logger.debug("Created WhatsApp city menu", extra={
                'total_cities': len(cities),
                'displayed_cities': len(city_list)
            })
            return menu_text

    @staticmethod
    @log_operation("create_whatsapp_rooms_keyboard")
    def create_rooms_keyboard(selected_rooms=None):
        """Create room selection menu text for WhatsApp"""
        menu_text = (
            "🛏️ Виберіть кількість кімнат:\n\n"
            "1. 1 кімната\n"
            "2. 2 кімнати\n"
            "3. 3 кімнати\n"
            "4. 4 кімнати\n"
            "5. 5 кімнат\n"
            "6. Будь-яка кількість кімнат\n\n"
            "Ви можете вибрати кілька варіантів, розділивши їх комами, наприклад: 1,2,3"
        )

        logger.debug("Created WhatsApp rooms menu")
        return menu_text

    @staticmethod
    @log_operation("create_whatsapp_price_keyboard")
    def create_price_keyboard(city):
        """Create price range selection menu text for WhatsApp"""
        with log_context(logger, city=city):
            intervals = get_price_ranges(city)
            options = []

            for i, (low, high) in enumerate(intervals):
                if high is None:
                    options.append(f"{i + 1}. Більше {low} грн.")
                else:
                    if low == 0:
                        options.append(f"{i + 1}. До {high} грн.")
                    else:
                        options.append(f"{i + 1}. {low}-{high} грн.")

            menu_text = (
                    "💰 Виберіть діапазон цін (грн):\n\n"
                    + "\n".join(options)
            )

            logger.debug("Created WhatsApp price menu", extra={
                'city': city,
                'intervals_count': len(intervals)
            })
            return menu_text

    @staticmethod
    @log_operation("create_whatsapp_confirmation_keyboard")
    def create_confirmation_keyboard():
        """Create subscription confirmation text for WhatsApp"""
        menu_text = (
            "Для підтвердження введіть одну з наступних команд:\n\n"
            "1. Підписатися - щоб підтвердити вибір\n"
            "2. Редагувати - щоб змінити параметри\n"
            "3. Розширений - для розширеного пошуку"
        )

        logger.debug("Created WhatsApp confirmation menu")
        return menu_text

    @staticmethod
    @log_operation("create_whatsapp_edit_parameters_keyboard")
    def create_edit_parameters_keyboard():
        """Create parameter editing menu text for WhatsApp"""
        menu_text = (
            "Оберіть параметр для редагування (введіть цифру):\n\n"
            "1. Тип нерухомості\n"
            "2. Місто\n"
            "3. Кількість кімнат\n"
            "4. Діапазон цін\n"
            "5. Скасувати редагування"
        )

        logger.debug("Created WhatsApp edit parameters menu")
        return menu_text