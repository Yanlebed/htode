# services/telegram_service/app/handlers/payment.py

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..bot import dp
from common.db.operations import get_db_user_id_by_telegram_id
from ..payment.wayforpay import create_payment_form_url

# Import service logger and logging utilities
from ... import logger
from common.utils.logging_config import log_operation, log_context


@dp.message_handler(lambda msg: msg.text == "💳 Оплатити підписку")
@log_operation("payment_handler")
async def payment_handler(message: types.Message):
    """Handle subscription payment request"""
    telegram_id = message.from_user.id

    with log_context(logger, telegram_id=telegram_id, action="payment_request"):
        db_user_id = get_db_user_id_by_telegram_id(telegram_id)

        if not db_user_id:
            logger.warning("User not found for payment request", extra={"telegram_id": telegram_id})
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
        logger.info("Payment options presented", extra={"telegram_id": telegram_id})


@dp.callback_query_handler(lambda c: c.data.startswith("pay_"))
@log_operation("process_payment")
async def process_payment(callback_query: types.CallbackQuery):
    """Process payment button click"""
    telegram_id = callback_query.from_user.id

    with log_context(logger, telegram_id=telegram_id, callback_data=callback_query.data):
        # Extract amount and period from callback data
        parts = callback_query.data.split("_")
        amount = float(parts[1])
        period = parts[2]

        db_user_id = get_db_user_id_by_telegram_id(telegram_id)

        # Create payment URL
        payment_url = create_payment_form_url(db_user_id, amount, period)

        if not payment_url:
            logger.error("Failed to create payment URL", extra={
                "telegram_id": telegram_id,
                "amount": amount,
                "period": period
            })
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

        logger.info("Payment URL created and sent", extra={
            "telegram_id": telegram_id,
            "amount": amount,
            "period": period
        })