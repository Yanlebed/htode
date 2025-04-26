# services/telegram_service/app/handlers/payment.py

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..bot import dp
from common.db.models import get_db_user_id_by_telegram_id
from ..payment.wayforpay import create_payment_form_url


@dp.message_handler(lambda msg: msg.text == "💳 Оплатити підписку")
async def payment_handler(message: types.Message):
    """Handle subscription payment request"""
    telegram_id = message.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    if not db_user_id:
        await message.answer("Спочатку потрібно зареєструватися. Використайте команду /start.")
        return

    # Create payment keyboard with options
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("1 місяць - 99 грн", callback_data="pay_99_1month"),
        InlineKeyboardButton("3 місяці - 269 грн", callback_data="pay_269_3months")
    )
    keyboard.add(
        InlineKeyboardButton("6 місяців - 499 грн", callback_data="pay_499_6months"),
        InlineKeyboardButton("1 рік - 899 грн", callback_data="pay_899_12months")
    )

    await message.answer(
        "Оберіть тарифний план для оплати підписки:",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data.startswith("pay_"))
async def process_payment(callback_query: types.CallbackQuery):
    """Process payment button click"""
    # Extract amount and period from callback data
    parts = callback_query.data.split("_")
    amount = float(parts[1])
    period = parts[2]

    telegram_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    # Create payment URL
    payment_url = create_payment_form_url(db_user_id, amount, period)

    if not payment_url:
        await callback_query.message.answer("На жаль, не вдалося створити платіж. Спробуйте пізніше.")
        await callback_query.answer()
        return

    # Send payment link
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Оплатити", url=payment_url)
    )

    await callback_query.message.answer(
        f"Для оплати підписки на {period} натисніть кнопку нижче:",
        reply_markup=keyboard
    )
    await callback_query.answer()
