import logging
from aiogram import types
from aiogram.dispatcher import FSMContext
from ..bot import dp, bot
from ..states.support_states import SupportStates
from ..keyboards import support_category_keyboard, support_redirect_keyboard, main_menu_keyboard

logger = logging.getLogger(__name__)


@dp.message_handler(lambda msg: msg.text == "🧑‍💻 Техпідтримка")
async def handle_support_command(message: types.Message, state: FSMContext):
    """
    Start the support conversation by asking the user to choose a category.
    """
    await message.answer("Будь ласка, оберіть категорію звернення:", reply_markup=support_category_keyboard())
    await SupportStates.waiting_for_category.set()


@dp.message_handler(lambda msg: msg.text in ["Оплата", "Технічні проблеми", "Інше"],
                    state=SupportStates.waiting_for_category)
async def process_support_category(message: types.Message, state: FSMContext):
    """
    Process the chosen support category.
    Based on the selection, generate a template message.
    """
    category = message.text
    if category == "Оплата":
        template = "Привіт! У мене є питання щодо оплати. Будь ласка, допоможіть розібратись."
    elif category == "Технічні проблеми":
        template = "Привіт! Я зіткнувся з технічною проблемою. Опис проблеми: "
    elif category == "Інше":
        template = "Привіт! У мене інше питання. Прошу допомоги: "
    else:
        template = "Привіт! У мене є питання."

    await state.finish()  # End the FSM as no further input is needed
    # Build an inline keyboard to redirect the user to support.
    # You can pass the lower-cased category as a parameter so the support system knows the context.
    kb = support_redirect_keyboard(template_data=category.lower())

    # Send the template message along with the inline button.
    await message.answer("Будь ласка, надішліть наступне повідомлення до техпідтримки.")
    await message.answer(f"{template}", reply_markup=kb)
    # await message.answer(f"Будь ласка, надішліть наступне повідомлення до техпідтримки:\n\n{template}",
    #                      reply_markup=kb)
    # Optionally, also display the main menu after.
    await message.answer("Повернутися в головне меню", reply_markup=main_menu_keyboard())
