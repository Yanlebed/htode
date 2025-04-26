# services/viber_service/app/handlers/phone_verification.py

import logging
from ..bot import state_manager
from ..utils.message_utils import safe_send_message
from common.verification.phone_service import (
    create_verification_code,
    verify_code,
    link_messenger_account,
    get_user_by_phone,
    transfer_subscriptions
)
from common.db.models import get_or_create_user

logger = logging.getLogger(__name__)

# Define state constants
STATE_WAITING_FOR_PHONE = "waiting_for_phone"
STATE_WAITING_FOR_CODE = "waiting_for_code"
STATE_WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"


async def start_phone_verification(user_id):
    """
    Start the phone verification process

    Args:
        user_id: Viber user ID
    """
    # Create keyboard for phone entry
    keyboard = {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Скасувати",
                "ActionType": "reply",
                "ActionBody": "cancel_verification"
            }
        ]
    }

    await safe_send_message(
        user_id,
        "Для додавання номера телефону і єдиного входу з різних пристроїв, "
        "будь ласка, введіть свій номер телефону в міжнародному форматі, "
        "наприклад +380991234567",
        keyboard=keyboard
    )

    # Update user state
    await state_manager.update_state(user_id, {
        "state": STATE_WAITING_FOR_PHONE
    })


async def handle_phone_input(user_id, text):
    """
    Handle phone number input

    Args:
        user_id: Viber user ID
        text: Message text containing phone number
    """
    if text == "cancel_verification":
        await cancel_verification(user_id)
        return

    # Clean the phone number
    phone_number = ''.join(c for c in text if c.isdigit() or c == '+')
    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number

    # Store the phone number in state
    await state_manager.update_state(user_id, {
        "phone_number": phone_number,
        "state": STATE_WAITING_FOR_CODE
    })

    # Generate verification code
    code = create_verification_code(phone_number)

    # Create keyboard for code entry
    keyboard = {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Скасувати",
                "ActionType": "reply",
                "ActionBody": "cancel_verification"
            }
        ]
    }

    # In production, send code via SMS
    # For development, show in chat
    await safe_send_message(
        user_id,
        f"Код підтвердження відправлено на номер {phone_number}.\n\n"
        f"⚠️ Для тестування, ось ваш код: {code}\n\n"
        "У реальному додатку код буде надіслано через SMS.",
        keyboard=keyboard
    )


async def handle_verification_code(user_id, code):
    """
    Handle verification code entry

    Args:
        user_id: Viber user ID
        code: Verification code
    """
    if code == "cancel_verification":
        await cancel_verification(user_id)
        return

    # Get stored state
    user_data = await state_manager.get_state(user_id) or {}
    phone_number = user_data.get('phone_number')

    if not phone_number:
        await safe_send_message(
            user_id,
            "Сталася помилка. Будь ласка, спробуйте знову."
        )
        await state_manager.update_state(user_id, {
            "state": "start"
        })
        return

    # Verify the code
    success, error_message = verify_code(phone_number, code)

    if not success:
        await safe_send_message(
            user_id,
            f"Помилка: {error_message}. Будь ласка, спробуйте ще раз."
        )
        return

    # Code verified successfully
    # Get current user in DB
    current_user_id = get_or_create_user(user_id, messenger_type="viber")

    # Check if a user with this phone already exists
    existing_user = get_user_by_phone(phone_number)

    if existing_user and existing_user.get('viber_id') != user_id:
        # User exists with this phone but has a different Viber ID
        # Ask for confirmation to merge accounts
        await state_manager.update_state(user_id, {
            "existing_user_id": existing_user['id'],
            "current_user_id": current_user_id,
            "state": STATE_WAITING_FOR_CONFIRMATION
        })

        # Create confirmation keyboard
        keyboard = {
            "Type": "keyboard",
            "Buttons": [
                {
                    "Columns": 3,
                    "Rows": 1,
                    "Text": "Так",
                    "ActionType": "reply",
                    "ActionBody": "confirm_merge"
                },
                {
                    "Columns": 3,
                    "Rows": 1,
                    "Text": "Ні",
                    "ActionType": "reply",
                    "ActionBody": "cancel_merge"
                }
            ]
        }

        await safe_send_message(
            user_id,
            "Цей номер телефону вже пов'язаний з іншим обліковим записом.\n\n"
            "Бажаєте об'єднати дані з вашого поточного облікового запису з цим номером телефону?",
            keyboard=keyboard
        )
    else:
        # No conflict, proceed with linking
        await handle_account_linking(user_id, phone_number, current_user_id)


async def handle_merge_confirmation(user_id, response):
    """
    Handle merge confirmation response

    Args:
        user_id: Viber user ID
        response: User's response ("confirm_merge" or "cancel_merge")
    """
    # Get stored state
    user_data = await state_manager.get_state(user_id) or {}
    existing_user_id = user_data.get('existing_user_id')
    current_user_id = user_data.get('current_user_id')
    phone_number = user_data.get('phone_number')

    if response == "confirm_merge":
        # User confirmed merge
        # Transfer data before linking
        if current_user_id and current_user_id != existing_user_id:
            transfer_subscriptions(current_user_id, existing_user_id)

        # Link the current Viber ID to the existing account with the phone number
        user_id_db = link_messenger_account(phone_number, "viber", user_id)

        # Create main menu keyboard
        keyboard = {
            "Type": "keyboard",
            "Buttons": [
                {
                    "Columns": 6,
                    "Rows": 1,
                    "Text": "Головне меню",
                    "ActionType": "reply",
                    "ActionBody": "main_menu"
                }
            ]
        }

        await safe_send_message(
            user_id,
            "Ваші облікові записи успішно об'єднано!\n\n"
            "Тепер ви можете використовувати свою підписку та налаштування на всіх пристроях.",
            keyboard=keyboard
        )
    else:
        # User declined merge
        keyboard = {
            "Type": "keyboard",
            "Buttons": [
                {
                    "Columns": 6,
                    "Rows": 1,
                    "Text": "Головне меню",
                    "ActionType": "reply",
                    "ActionBody": "main_menu"
                }
            ]
        }

        await safe_send_message(
            user_id,
            "Операцію скасовано. Ваш номер телефону не було прив'язано.",
            keyboard=keyboard
        )

    # Reset state
    await state_manager.update_state(user_id, {
        "state": "start"
    })


async def handle_account_linking(user_id, phone_number, current_user_id):
    """
    Handle linking a phone number to an account without conflicts

    Args:
        user_id: Viber user ID
        phone_number: Phone number to link
        current_user_id: User's current DB ID
    """
    # Link the phone number to the user
    user_id_db = link_messenger_account(phone_number, "viber", user_id)

    # Create main menu keyboard
    keyboard = {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Головне меню",
                "ActionType": "reply",
                "ActionBody": "main_menu"
            }
        ]
    }

    await safe_send_message(
        user_id,
        "Ваш номер телефону успішно підтверджено!\n\n"
        "Тепер ви можете використовувати свою підписку та налаштування на всіх пристроях та в різних месенджерах.",
        keyboard=keyboard
    )

    # Reset state
    await state_manager.update_state(user_id, {
        "state": "start"
    })


async def cancel_verification(user_id):
    """
    Cancel the verification process

    Args:
        user_id: Viber user ID
    """
    # Create main menu keyboard
    keyboard = {
        "Type": "keyboard",
        "Buttons": [
            {
                "Columns": 6,
                "Rows": 1,
                "Text": "Головне меню",
                "ActionType": "reply",
                "ActionBody": "main_menu"
            }
        ]
    }

    await safe_send_message(
        user_id,
        "Верифікацію скасовано.",
        keyboard=keyboard
    )

    # Reset state
    await state_manager.update_state(user_id, {
        "state": "start"
    })