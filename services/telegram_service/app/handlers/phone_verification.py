# services/telegram_service/app/handlers/phone_verification.py

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from ..bot import dp
from ..utils.message_utils import safe_send_message, safe_answer_callback_query
from common.verification.phone_service import (
    create_verification_code,
    verify_code,
    link_messenger_account,
    get_user_by_phone,
    transfer_subscriptions
)
from common.db.operations import get_db_user_id_by_telegram_id
from ..keyboards import (
    phone_request_keyboard,
    verification_code_keyboard,
    verification_success_keyboard,
    main_menu_keyboard
)

# Import service logger and logging utilities
from ... import logger
from common.utils.logging_config import log_operation, log_context


class PhoneVerificationStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_confirmation = State()


@dp.message_handler(lambda msg: msg.text == "📱 Додати номер телефону")
@log_operation("start_phone_verification")
async def start_phone_verification(message: types.Message, state: FSMContext):
    """
    Start the phone verification process when user selects the menu option
    """
    user_id = message.from_user.id

    with log_context(logger, user_id=user_id, action="start_phone_verification"):
        await safe_send_message(
            chat_id=message.chat.id,
            text=(
                "Для додавання номера телефону і єдиного входу з різних пристроїв, "
                "будь ласка, надайте свій номер телефону.\n\n"
                "Ви можете скористатися кнопкою 'Поділитися номером телефону' або "
                "ввести номер вручну в міжнародному форматі (наприклад, +380991234567)."
            ),
            reply_markup=phone_request_keyboard()
        )
        await PhoneVerificationStates.waiting_for_phone.set()
        logger.info("Phone verification started", extra={"user_id": user_id})


@dp.message_handler(content_types=types.ContentType.CONTACT, state=PhoneVerificationStates.waiting_for_phone)
async def handle_contact(message: types.Message, state: FSMContext):
    """
    Handle phone number shared via contact
    """
    phone_number = message.contact.phone_number
    await process_phone_number(message, state, phone_number)


@dp.message_handler(state=PhoneVerificationStates.waiting_for_phone)
async def handle_phone_text(message: types.Message, state: FSMContext):
    """
    Handle phone number entered as text
    """
    phone_number = message.text.strip()
    await process_phone_number(message, state, phone_number)


async def process_phone_number(message: types.Message, state: FSMContext, phone_number: str):
    """
    Process the provided phone number and send verification code
    """
    # Store the phone number in state
    await state.update_data(phone_number=phone_number)

    # Generate and send verification code
    code = create_verification_code(phone_number)

    # In a production environment, you would send this code via SMS
    # For testing purposes, we're showing it directly in the chat
    await safe_send_message(
        chat_id=message.chat.id,
        text=(
            f"Код підтвердження відправлено на номер {phone_number}.\n\n"
            f"⚠️ Для тестування, ось ваш код: {code}\n\n"
            "У реальному додатку код буде надіслано через SMS."
        ),
        reply_markup=verification_code_keyboard()
    )

    # Move to the next state
    await PhoneVerificationStates.waiting_for_code.set()


@dp.message_handler(state=PhoneVerificationStates.waiting_for_code)
async def handle_verification_code(message: types.Message, state: FSMContext):
    """
    Verify the code entered by the user
    """
    code = message.text.strip()
    user_data = await state.get_data()
    phone_number = user_data.get('phone_number')

    if not phone_number:
        await safe_send_message(
            chat_id=message.chat.id,
            text="Сталася помилка. Будь ласка, спробуйте знову."
        )
        await state.finish()
        return

    # Verify the code
    success, error_message = verify_code(phone_number, code)

    if not success:
        await safe_send_message(
            chat_id=message.chat.id,
            text=f"Помилка: {error_message}. Будь ласка, спробуйте знову."
        )
        return

    # Code verified successfully
    telegram_id = message.from_user.id

    # Check if a user with this phone already exists
    existing_user = get_user_by_phone(phone_number)

    # Get the current user's ID in our database
    current_user_id = get_db_user_id_by_telegram_id(telegram_id)

    if existing_user and existing_user.get('telegram_id') != telegram_id:
        # User exists with this phone number but has a different telegram_id
        # Ask for confirmation to merge accounts
        await state.update_data(
            existing_user_id=existing_user['id'],
            current_user_id=current_user_id
        )

        await safe_send_message(
            chat_id=message.chat.id,
            text=(
                "Цей номер телефону вже пов'язаний з іншим обліковим записом.\n\n"
                "Бажаєте об'єднати дані з вашого поточного облікового запису з цим номером телефону?"
            ),
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("Так, об'єднати", callback_data="merge_accounts"),
                types.InlineKeyboardButton("Ні, скасувати", callback_data="cancel_merge")
            )
        )

        await PhoneVerificationStates.waiting_for_confirmation.set()
    else:
        # No conflict, proceed with linking
        await handle_account_linking(message, state, phone_number, telegram_id, current_user_id)


@dp.callback_query_handler(lambda c: c.data == "merge_accounts", state=PhoneVerificationStates.waiting_for_confirmation)
async def confirm_merge_accounts(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Handle account merging confirmation
    """
    user_data = await state.get_data()
    existing_user_id = user_data.get('existing_user_id')
    current_user_id = user_data.get('current_user_id')
    phone_number = user_data.get('phone_number')

    # Link current Telegram ID to the existing account
    telegram_id = callback_query.from_user.id

    # Transfer data before linking
    if current_user_id and current_user_id != existing_user_id:
        transfer_subscriptions(current_user_id, existing_user_id)

    # Link the current Telegram ID to the existing account with the phone number
    user_id = link_messenger_account(phone_number, "telegram", str(telegram_id))

    await safe_send_message(
        chat_id=callback_query.message.chat.id,
        text=(
            "Ваші облікові записи успішно об'єднано!\n\n"
            "Тепер ви можете використовувати свою підписку та налаштування на всіх пристроях."
        ),
        reply_markup=verification_success_keyboard()
    )

    await state.finish()
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data == "cancel_merge", state=PhoneVerificationStates.waiting_for_confirmation)
async def cancel_merge_accounts(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Handle cancellation of account merging
    """
    await safe_send_message(
        chat_id=callback_query.message.chat.id,
        text="Операцію скасовано. Ваш номер телефону не було прив'язано.",
        reply_markup=main_menu_keyboard()
    )

    await state.finish()
    await safe_answer_callback_query(callback_query.id)


async def handle_account_linking(message: types.Message, state: FSMContext, phone_number: str, telegram_id: int,
                                 user_id: int):
    """
    Handle linking a phone number to an account
    """
    # Link the phone number to the user
    user_id = link_messenger_account(phone_number, "telegram", str(telegram_id))

    await safe_send_message(
        chat_id=message.chat.id,
        text=(
            "Ваш номер телефону успішно підтверджено!\n\n"
            "Тепер ви можете використовувати свою підписку та налаштування на всіх пристроях та в різних месенджерах."
        ),
        reply_markup=verification_success_keyboard()
    )

    await state.finish()