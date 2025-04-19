# services/viber_service/app/keyboards.py

def create_main_menu_keyboard():
    """Create the main menu keyboard for Viber"""
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
                "Columns": 6,
                "Rows": 1,
                "Text": "🧑‍💻 Техпідтримка",
                "ActionType": "reply",
                "ActionBody": "🧑‍💻 Техпідтримка"
            }
        ]
    }


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
                "ActionBody": "property_type_apartment"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "Будинок",
                "ActionType": "reply",
                "ActionBody": "property_type_house"
            }
        ]
    }


def create_city_keyboard(cities):
    """
    Create keyboard for city selection

    Args:
        cities: List of available cities
    """
    buttons = []

    # Create a button for each city, arranged in rows of 2
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


def create_rooms_keyboard(selected_rooms=None):
    """
    Create keyboard for room selection

    Args:
        selected_rooms: List of already selected room counts
    """
    if selected_rooms is None:
        selected_rooms = []

    buttons = []

    # Add buttons for room counts 1-5
    for room in range(1, 6):
        # Mark selected rooms with a checkmark
        text = f"✅ {room}" if room in selected_rooms else f"{room}"
        buttons.append({
            "Columns": 1,
            "Rows": 1,
            "Text": text,
            "ActionType": "reply",
            "ActionBody": f"rooms_{room}"
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


def get_price_ranges(city):
    """
    Returns a list of (min_price, max_price) tuples
    for the given city.
    If max_price is None, it means "more than min_price".
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


def create_price_keyboard(city):
    """
    Create keyboard for price range selection

    Args:
        city: City name to determine appropriate price ranges
    """
    intervals = get_price_ranges(city)
    buttons = []

    # Create a button for each price range
    for (low, high) in intervals:
        if high is None:
            label = f"Більше {low}"
            action_body = f"price_{low}_any"
        else:
            # E.g. "0-5000 UAH", "5000-7000 UAH"
            if low == 0:
                label = f"До {high}"  # "up to X"
            else:
                label = f"{low}-{high}"
            action_body = f"price_{low}_{high}"

        buttons.append({
            "Columns": 3,
            "Rows": 1,
            "Text": label,
            "ActionType": "reply",
            "ActionBody": action_body
        })

    return {
        "Type": "keyboard",
        "ButtonsGroupColumns": 6,
        "ButtonsGroupRows": 2,
        "Buttons": buttons
    }


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


def create_favorites_navigation_keyboard(current_index, total_favorites):
    """
    Create keyboard for navigating favorites

    Args:
        current_index: Current position in favorites
        total_favorites: Total number of favorites
    """
    buttons = []

    # Only show Previous if not at the first item
    if current_index > 0:
        buttons.append({
            "Columns": 3,
            "Rows": 1,
            "Text": "◀️ Попереднє",
            "ActionType": "reply",
            "ActionBody": f"fav_prev:{current_index}"
        })

    # Only show Next if not at the last item
    if current_index < total_favorites - 1:
        buttons.append({
            "Columns": 3,
            "Rows": 1,
            "Text": "Наступне ▶️",
            "ActionType": "reply",
            "ActionBody": f"fav_next:{current_index}"
        })

    # Add action buttons
    buttons.append({
        "Columns": 6,
        "Rows": 1,
        "Text": "Більше фото",
        "ActionType": "reply",
        "ActionBody": "more_photos"
    })

    buttons.append({
        "Columns": 6,
        "Rows": 1,
        "Text": "Подзвонити",
        "ActionType": "reply",
        "ActionBody": "call_contact"
    })

    buttons.append({
        "Columns": 3,
        "Rows": 1,
        "Text": "Видалити з обраних",
        "ActionType": "reply",
        "ActionBody": f"rm_fav:{current_index}"
    })

    buttons.append({
        "Columns": 3,
        "Rows": 1,
        "Text": "Повний опис",
        "ActionType": "reply",
        "ActionBody": "show_more"
    })

    return {
        "Type": "keyboard",
        "ButtonsGroupColumns": 6,
        "ButtonsGroupRows": 3,
        "Buttons": buttons
    }


def create_payment_keyboard():
    """Create keyboard for payment options"""
    return {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "1 місяць - 99 грн",
                "ActionType": "reply",
                "ActionBody": "pay_99_1month"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "3 місяці - 269 грн",
                "ActionType": "reply",
                "ActionBody": "pay_269_3months"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "6 місяців - 499 грн",
                "ActionType": "reply",
                "ActionBody": "pay_499_6months"
            },
            {
                "Columns": 3,
                "Rows": 1,
                "Text": "1 рік - 899 грн",
                "ActionType": "reply",
                "ActionBody": "pay_899_12months"
            },
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "↪️ Назад",
                "ActionType": "reply",
                "ActionBody": "back_to_menu"
            }
        ]
    }


def create_support_category_keyboard():
    """Create keyboard for support categories"""
    return {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Оплата",
                "ActionType": "reply",
                "ActionBody": "support_payment"
            },
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Технічні проблеми",
                "ActionType": "reply",
                "ActionBody": "support_technical"
            },
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Інше",
                "ActionType": "reply",
                "ActionBody": "support_other"
            },
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "↪️ Назад",
                "ActionType": "reply",
                "ActionBody": "back_to_menu"
            }
        ]
    }
