# services/telegram_service/app/keyboards.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

SMALLER_CITIES = {
    'Чернівці', 'Черкаси', 'Хмельницький', 'Херсон', 'Ужгород',
    'Тернопіль', 'Суми', 'Рівне', 'Полтава', 'Миколаїв', 'Луцьк',
    'Кропивницький', 'Вінниця', 'Житомир', 'Запоріжжя', 'Івано-Франківськ'
    # Add others here if needed
}

BIGGER_CITIES = {'Харків', 'Дніпро', 'Одеса', 'Львів'}


def get_price_ranges(city: str):
    """
    Returns a list of (min_price, max_price) tuples
    for the given city.
    If max_price is None, it means "more than min_price".
    """
    if city == "Київ":
        # up to 15000, 15000–20000, 20000–30000, more than 30000
        return [(0, 15000), (15000, 20000), (20000, 30000), (30000, None)]
    elif city in BIGGER_CITIES:
        # up to 7000, 7000–10000, 10000–15000, more than 15000
        return [(0, 7000), (7000, 10000), (10000, 15000), (15000, None)]
    else:
        # Default to "smaller" city intervals
        # up to 5000, 5000–7000, 7000–10000, more than 10000
        return [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]


def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Моя підписка", callback_data="menu_my_subscription"),
        InlineKeyboardButton("Як це працює?", callback_data="menu_how_to_use"),
        InlineKeyboardButton("Техпідтримка", callback_data="menu_tech_support")
    )
    return keyboard


def subscription_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Відключити", callback_data="subs_disable"),
        InlineKeyboardButton("Включити", callback_data="subs_enable"),
        InlineKeyboardButton("Редагувати", callback_data="subs_edit"),
        InlineKeyboardButton("Назад", callback_data="subs_back")
    )
    return keyboard


def how_to_use_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Написати у техпідтримку", callback_data="contact_support"),
        InlineKeyboardButton("Назад", callback_data="main_menu")
    )
    return keyboard


def tech_support_keyboard():
    # Or just go directly to chat, but here's an example
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Назад", callback_data="main_menu")
    )
    return keyboard


def property_type_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Квартира", callback_data="property_type_apartment"),
        InlineKeyboardButton("Будинок", callback_data="property_type_house"),
    )
    return keyboard


def grouped(iterable, n):
    return zip(*[iter(iterable)] * n)


def city_keyboard(cities):
    keyboard = InlineKeyboardMarkup(row_width=2)
    for city_1, city_2 in grouped(cities, 2):
        keyboard.add(
            InlineKeyboardButton(city_1, callback_data=f"city_{city_1.lower()}"),
            InlineKeyboardButton(city_2, callback_data=f"city_{city_2.lower()}"),
        )
    return keyboard


def rooms_keyboard(selected_rooms=None):
    keyboard = InlineKeyboardMarkup(row_width=3)
    for rooms in range(1, 6):
        if selected_rooms and rooms in selected_rooms:
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
    return keyboard


def price_keyboard(city: str):
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

    return keyboard


def confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Розширений пошук", callback_data="advanced_search"),
        InlineKeyboardButton("Редагувати", callback_data="edit_parameters"),
        InlineKeyboardButton("Підписатися", callback_data="subscribe")
    )
    return keyboard


def edit_parameters_keyboard():
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
    return keyboard


def floor_keyboard(floor_opts=None):
    """
    floor_opts is a dict with boolean flags like:
      "not_first", "not_last", "floor_max_6", "floor_max_10", "floor_max_17", "only_last"
    We'll return an InlineKeyboard with toggles for each.
    """
    if floor_opts is None:
        floor_opts = {
            "not_first": False,
            "not_last": False,
            "floor_max_6": False,
            "floor_max_10": False,
            "floor_max_17": False,
            "only_last": False
        }

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

    return kb
