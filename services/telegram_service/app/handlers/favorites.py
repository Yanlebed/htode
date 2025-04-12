from aiogram import types
from ..bot import dp

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from common.db.models import add_favorite_ad, remove_favorite_ad, list_favorites, get_db_user_id_by_telegram_id
from common.config import build_ad_text


@dp.callback_query_handler(lambda c: c.data.startswith("add_fav:"))
async def handle_add_fav(callback_query: types.CallbackQuery):
    ad_id_str = callback_query.data.split("add_fav:")[1]
    ad_id = int(ad_id_str)
    telegram_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    try:
        add_favorite_ad(db_user_id, ad_id)
        await callback_query.answer("Додано до обраних!")
    except ValueError as e:
        await callback_query.answer(str(e), show_alert=True)
    except Exception as e:
        await callback_query.answer("Сталася помилка.", show_alert=True)


@dp.message_handler(lambda msg: msg.text == "Мої обрані")
async def show_favorites(message: types.Message):
    telegram_id = message.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)
    favs = list_favorites(db_user_id)
    if not favs:
        await message.answer("Немає обраних оголошень.")
        return

    for f in favs:
        text = build_ad_text(f)  # reuse your function
        buttons = InlineKeyboardMarkup()
        buttons.add(InlineKeyboardButton("Видалити з обраних", callback_data=f"rm_fav:{f['ad_id']}"))
        await message.answer(text, reply_markup=buttons)


@dp.callback_query_handler(lambda c: c.data.startswith("rm_fav:"))
async def handle_remove_fav(callback_query: types.CallbackQuery):
    ad_id = int(callback_query.data.split(":")[1])
    db_user_id = get_db_user_id_by_telegram_id(callback_query.from_user.id)
    remove_favorite_ad(db_user_id, ad_id)
    await callback_query.answer("Видалено з обраних.")
