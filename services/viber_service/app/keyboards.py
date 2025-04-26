# services/viber_service/app/keyboards.py
import logging
from common.messaging.keyboard_utils import KeyboardFactory

logger = logging.getLogger(__name__)

# Re-export keyboard creation functions with platform set to "viber"
def create_main_menu_keyboard():
    """Create the main menu keyboard for Viber"""
    return KeyboardFactory.create_keyboard("viber", "main_menu")

def create_property_type_keyboard():
    """Create keyboard for property type selection"""
    return KeyboardFactory.create_keyboard("viber", "property_type")

def create_city_keyboard(cities):
    """Create keyboard for city selection"""
    return KeyboardFactory.create_keyboard("viber", "city", cities=cities)

def create_rooms_keyboard(selected_rooms=None):
    """Create keyboard for room selection"""
    return KeyboardFactory.create_keyboard("viber", "rooms", selected_rooms=selected_rooms)

def create_price_keyboard(city):
    """Create keyboard for price range selection"""
    return KeyboardFactory.create_keyboard("viber", "price", city=city)

def create_confirmation_keyboard():
    """Create keyboard for subscription confirmation"""
    return KeyboardFactory.create_keyboard("viber", "confirmation")

def create_edit_parameters_keyboard():
    """Create keyboard for parameter editing"""
    return KeyboardFactory.create_keyboard("viber", "edit_parameters")

# Additional, more specialized keyboards not included in the common factory

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