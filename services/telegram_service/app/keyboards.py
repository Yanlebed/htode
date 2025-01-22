# services/telegram_service/app/keyboards.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Моя подписка", callback_data="menu_my_subscription"),
        InlineKeyboardButton("Как это работает?", callback_data="menu_how_to_use"),
        InlineKeyboardButton("Техподдержка", callback_data="menu_tech_support")
    )
    return keyboard


def subscription_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Отключить", callback_data="subs_disable"),
        InlineKeyboardButton("Включить", callback_data="subs_enable"),
        InlineKeyboardButton("Изменить", callback_data="subs_edit"),
        InlineKeyboardButton("Вернуться в меню", callback_data="subs_back")
    )
    return keyboard


def how_to_use_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Написать в техподдержку", callback_data="contact_support"),
        InlineKeyboardButton("Вернуться в меню", callback_data="main_menu")
    )
    return keyboard


def tech_support_keyboard():
    # Or just go directly to chat, but here's an example
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Вернуться в меню", callback_data="main_menu")
    )
    return keyboard


def property_type_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Квартира", callback_data="property_type_apartment"),
        InlineKeyboardButton("Дом", callback_data="property_type_house"),
        InlineKeyboardButton("Комната", callback_data="property_type_room")
    )
    return keyboard


def city_keyboard(cities):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for city in cities:
        keyboard.add(InlineKeyboardButton(city, callback_data=f"city_{city.lower()}"))
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
        InlineKeyboardButton("Готово", callback_data="rooms_done"),
        InlineKeyboardButton("Не важно", callback_data="rooms_any")
    )
    return keyboard


def price_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("До 500$", callback_data="price_0_500"),
        InlineKeyboardButton("500$ - 1000$", callback_data="price_500_1000"),
        InlineKeyboardButton("1000$ - 1500$", callback_data="price_1000_1500"),
        InlineKeyboardButton("Более 1500$", callback_data="price_1500_any")
    )
    return keyboard


def listing_date_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Сегодня", callback_data="date_today"),
        InlineKeyboardButton("Последние 3 дня", callback_data="date_3_days"),
        InlineKeyboardButton("Последняя неделя", callback_data="date_week"),
        InlineKeyboardButton("Последний месяц", callback_data="date_month"),
        InlineKeyboardButton("За всё время", callback_data="date_all_time")
    )
    return keyboard


def confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Редактировать параметры", callback_data="edit_parameters"),
        InlineKeyboardButton("Подписаться на поиск", callback_data="subscribe")
    )
    return keyboard


def edit_parameters_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Тип недвижимости", callback_data="edit_property_type"),
        InlineKeyboardButton("Город", callback_data="edit_city"),
        InlineKeyboardButton("Количество комнат", callback_data="edit_rooms"),
        InlineKeyboardButton("Диапазон цен", callback_data="edit_price"),
        InlineKeyboardButton("Дата размещения", callback_data="edit_listing_date"),
        InlineKeyboardButton("Отмена", callback_data="cancel_edit")
    )
    return keyboard
