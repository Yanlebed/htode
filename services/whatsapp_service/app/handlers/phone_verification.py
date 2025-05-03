# services/whatsapp_service/app/handlers/phone_verification.py

from ..bot import sanitize_phone_number, get_user_state, update_user_state, set_user_state
from ..utils.message_utils import safe_send_message
from common.verification.phone_service import (
    create_verification_code,
    verify_code,
    link_messenger_account,
    get_user_by_phone,
    transfer_subscriptions
)
from common.db.operations import get_db_user_id_by_telegram_id
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from .. import logger

# Define states for the phone verification flow
STATE_WAITING_FOR_PHONE = "waiting_for_phone"
STATE_WAITING_FOR_CODE = "waiting_for_code"
STATE_WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"


@log_operation("start_phone_verification")
async def start_phone_verification(user_id, response=None):
    """
    Start the phone verification process.

    Args:
        user_id: User's WhatsApp ID
        response: Optional Twilio response for immediate reply
    """
    with log_context(logger, user_id=user_id):
        logger.info(f"Starting phone verification for user {user_id}")

        # For WhatsApp users, we already have their phone number from the Twilio user ID
        # We just need to confirm they want to use it for verification

        message = (
            "Щоб використовувати свою підписку на різних пристроях та в різних месенджерах, "
            "ми можемо верифікувати ваш номер телефону.\n\n"
            f"Ваш поточний номер: {user_id}\n\n"
            "Бажаєте використовувати цей номер для входу?\n"
            "Відправте 'Так' для підтвердження або введіть інший номер у міжнародному форматі."
        )

        if response:
            response.message(message)
        else:
            await safe_send_message(user_id, message)

        # Save state
        await set_user_state(user_id, {
            "state": STATE_WAITING_FOR_PHONE
        })

        logger.debug(f"Set state to {STATE_WAITING_FOR_PHONE} for user {user_id}")


@log_operation("handle_phone_input")
async def handle_phone_input(user_id, text, response=None):
    """
    Handle phone number input from user.

    Args:
        user_id: User's WhatsApp ID
        text: Message text (phone number or confirmation)
        response: Optional Twilio response for immediate reply
    """
    with log_context(logger, user_id=user_id, user_input=text):
        logger.info(f"Processing phone input for user {user_id}")

        # Get current state
        user_data = await get_user_state(user_id) or {}

        # Determine phone number to use
        if text.lower() in ['так', 'yes', 'да', '1']:
            # Use current WhatsApp number
            phone_number = sanitize_phone_number(user_id)
            logger.info(f"User {user_id} confirmed using WhatsApp number: {phone_number}")
        else:
            # Use user-entered number
            phone_number = sanitize_phone_number(text)
            logger.info(f"User {user_id} entered custom phone number: {phone_number}")

        # Store in state
        await update_user_state(user_id, {
            "phone_number": phone_number,
            "state": STATE_WAITING_FOR_CODE
        })

        # Generate verification code
        code = create_verification_code(phone_number)
        logger.info(f"Generated verification code for phone {phone_number}", extra={
            'code_exists': bool(code)
        })

        # In production, this would be sent via a separate SMS
        # For testing, show it in the chat
        message = (
            f"Код підтвердження відправлено на номер {phone_number}.\n\n"
            f"⚠️ Для тестування, ось ваш код: {code}\n\n"
            "У реальному додатку код буде надіслано через SMS."
        )

        if response:
            response.message(message)
        else:
            await safe_send_message(user_id, message)


@log_operation("handle_verification_code")
async def handle_verification_code(user_id, code, response=None):
    """
    Handle verification code entry.

    Args:
        user_id: User's WhatsApp ID
        code: Verification code entered by user
        response: Optional Twilio response for immediate reply
    """
    with log_context(logger, user_id=user_id, code_length=len(code)):
        logger.info(f"Processing verification code for user {user_id}")

        # Get stored state
        user_data = await get_user_state(user_id) or {}
        phone_number = user_data.get('phone_number')

        if not phone_number:
            logger.error(f"No phone number found in state for user {user_id}")
            message = "Сталася помилка. Будь ласка, спробуйте знову."
            if response:
                response.message(message)
            else:
                await safe_send_message(user_id, message)
            return

        # Verify the code
        success, error_message = verify_code(phone_number, code)
        logger.info(f"Code verification result for user {user_id}: success={success}")

        if not success:
            logger.warning(f"Verification failed for user {user_id}: {error_message}")
            message = f"Помилка: {error_message}. Будь ласка, спробуйте знову."
            if response:
                response.message(message)
            else:
                await safe_send_message(user_id, message)
            return

        # Code verified successfully
        # Check if a user with this phone already exists
        existing_user = get_user_by_phone(phone_number)

        logger.debug(f"Checking existing user for phone {phone_number}: {bool(existing_user)}")

        # Get the current user's ID in our database
        # For WhatsApp, we use the phone number as the ID
        current_user_id = get_db_user_id_by_telegram_id(user_id)

        if existing_user and existing_user.get('whatsapp_id') != user_id:
            logger.warning(f"Phone conflict detected for {phone_number} - account merge needed")
            # User exists with this phone but has a different WhatsApp ID
            # Ask for confirmation to merge accounts
            await update_user_state(user_id, {
                "existing_user_id": existing_user['id'],
                "current_user_id": current_user_id,
                "state": STATE_WAITING_FOR_CONFIRMATION
            })

            message = (
                "Цей номер телефону вже пов'язаний з іншим обліковим записом.\n\n"
                "Бажаєте об'єднати дані з вашого поточного облікового запису з цим номером телефону?\n"
                "Відправте 'Так' для підтвердження або 'Ні' для скасування."
            )

            if response:
                response.message(message)
            else:
                await safe_send_message(user_id, message)
        else:
            logger.info(f"No conflict detected, proceeding with account linking for user {user_id}")
            # No conflict, proceed with linking
            await handle_account_linking(user_id, phone_number, current_user_id, response)


@log_operation("handle_merge_confirmation")
async def handle_merge_confirmation(user_id, confirmation, response=None):
    """
    Handle account merge confirmation.

    Args:
        user_id: User's WhatsApp ID
        confirmation: User's confirmation response
        response: Optional Twilio response for immediate reply
    """
    with log_context(logger, user_id=user_id, confirmation=confirmation):
        logger.info(f"Processing merge confirmation for user {user_id}")

        # Get stored state
        user_data = await get_user_state(user_id) or {}
        existing_user_id = user_data.get('existing_user_id')
        current_user_id = user_data.get('current_user_id')
        phone_number = user_data.get('phone_number')

        if confirmation.lower() in ['так', 'yes', 'да', '1']:
            logger.info(f"User {user_id} confirmed account merge", extra={
                'existing_user_id': existing_user_id,
                'current_user_id': current_user_id
            })

            # User confirmed merge
            # Transfer data before linking
            if current_user_id and current_user_id != existing_user_id:
                logger.info(f"Transferring subscriptions from {current_user_id} to {existing_user_id}")
                transfer_subscriptions(current_user_id, existing_user_id)

            # Link the current WhatsApp ID to the existing account with the phone number
            user_id_clean = sanitize_phone_number(user_id)
            user_id_db = link_messenger_account(phone_number, "whatsapp", user_id_clean)

            logger.info(f"Successfully linked WhatsApp account {user_id} to database user {user_id_db}")

            message = (
                "Ваші облікові записи успішно об'єднано!\n\n"
                "Тепер ви можете використовувати свою підписку та налаштування на всіх пристроях."
            )
        else:
            logger.info(f"User {user_id} declined account merge")
            # User declined merge
            message = "Операцію скасовано. Ваш номер телефону не було прив'язано."

        # Reset state
        await set_user_state(user_id, {
            "state": "start"  # Return to main state
        })

        # Send response
        if response:
            response.message(message)
        else:
            await safe_send_message(user_id, message)


@log_operation("handle_account_linking")
async def handle_account_linking(user_id, phone_number, current_user_id, response=None):
    """
    Handle linking a phone number to an account without conflicts.

    Args:
        user_id: User's WhatsApp ID
        phone_number: Phone number to link
        current_user_id: User's current DB ID
        response: Optional Twilio response for immediate reply
    """
    with log_context(logger, user_id=user_id, phone_number=phone_number, current_user_id=current_user_id):
        logger.info(f"Linking phone {phone_number} to WhatsApp user {user_id}")

        # Link the WhatsApp ID to the phone number
        user_id_clean = sanitize_phone_number(user_id)
        user_id_db = link_messenger_account(phone_number, "whatsapp", user_id_clean)

        logger.info(f"Successfully linked phone {phone_number} to database user {user_id_db}")

        # Reset state
        await set_user_state(user_id, {
            "state": "start"  # Return to main state
        })

        message = (
            "Ваш номер телефону успішно підтверджено!\n\n"
            "Тепер ви можете використовувати свою підписку та налаштування на всіх пристроях та в різних месенджерах."
        )

        if response:
            response.message(message)
        else:
            await safe_send_message(user_id, message)