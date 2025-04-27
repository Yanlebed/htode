# services/telegram_service/app/handlers/advanced_handlers.py

import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import ParseMode, MediaGroup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import MessageNotModified
from ..bot import dp, bot
from ..states.basis_states import FilterStates
from ..keyboards import floor_keyboard
from common.db.operations import get_extra_images

logger = logging.getLogger(__name__)


@dp.callback_query_handler(lambda c: c.data == "advanced_search", state=FilterStates.waiting_for_confirmation)
async def advanced_search_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "return_to_advanced_menu", state="*")
async def return_to_advanced_menu_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_floor_max", state="*")
async def edit_floor_max_handler(callback_query: types.CallbackQuery, state: FSMContext):
    # Show some example floors from 1..25 or 1..10
    keyboard = InlineKeyboardMarkup(row_width=5)
    floors = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # Adjust as you like
    for f in floors:
        keyboard.insert(InlineKeyboardButton(str(f), callback_data=f"floor_max_{f}"))
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Виберіть максимальний поверх:", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("floor_max_"), state="*")
async def set_floor_max(callback_query: types.CallbackQuery, state: FSMContext):
    # parse the chosen floor
    chosen_floor = int(callback_query.data.split("_")[2])  # "floor_max_6" -> 6
    await state.update_data(floor_max=chosen_floor)

    await callback_query.message.answer(f"Максимальний поверх тепер {chosen_floor}.")
    # Optionally show advanced menu again
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "edit_is_not_first_floor", state="*")
async def edit_is_not_first_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Так", callback_data="is_not_first_floor_yes"))
    keyboard.add(InlineKeyboardButton("Ні", callback_data="is_not_first_floor_no"))
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Чи виключати перший поверх?", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("is_not_first_floor_"), state="*")
async def set_is_not_first_floor(callback_query: types.CallbackQuery, state: FSMContext):
    # either "yes" or "no"
    value = callback_query.data.split("_")[-1]  # yes / no
    # The actual param for flatfy would be `is_not_first_floor=yes` or `no`
    await state.update_data(is_not_first_floor=value)

    text = "Виключаю перший поверх" if value == "yes" else "Перший поверх дозволений"
    await callback_query.message.answer(text)
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "edit_last_floor", state="*")
async def edit_last_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Так", callback_data="last_floor_yes"),
        InlineKeyboardButton("Ні", callback_data="last_floor_no")
    )
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Виключати останній поверх?", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("last_floor_"), state="*")
async def set_last_floor(callback_query: types.CallbackQuery, state: FSMContext):
    value = callback_query.data.split("_")[-1]  # yes / no
    await state.update_data(last_floor=value)

    text = "Виключаю останній поверх" if value == "no" else "Тільки останній поверх"
    # Actually, for flatfy: "last_floor=no" means do not show last floor ads?
    await callback_query.message.answer(f"last_floor={value}")
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "pets_allowed", state="*")
async def edit_pets_allowed_handler(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Так", callback_data="pets_allowed_yes"),
        InlineKeyboardButton("Ні", callback_data="pets_allowed_no"),
    )
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("🐶🐈🐹 Чи дозволено з тваринами?", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("pets_allowed_"), state="*")
async def set_pets_allowed(callback_query: types.CallbackQuery, state: FSMContext):
    value = callback_query.data.split("_")[-1]  # yes / no / some
    mapped_values = {'yes': 'Так', 'no': 'Ні'}
    ua_lang_value = mapped_values.get(value)
    await state.update_data(pets_allowed_full=value)
    await callback_query.message.answer(f'Обрано: "{ua_lang_value}"')
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "without_broker", state="*")
async def edit_without_broker_handler(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Від власника", callback_data="without_broker_owner"),
        InlineKeyboardButton("Усі оголошення", callback_data="without_broker_all")
    )
    keyboard.add(InlineKeyboardButton("До списку параметрів", callback_data="return_to_advanced_menu"))

    await callback_query.message.answer("Виберіть вид оголошень:", reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("without_broker_"), state="*")
async def set_without_broker(callback_query: types.CallbackQuery, state: FSMContext):
    choice = callback_query.data.split("_")[-1]  # "owner" or "all"
    if choice == "owner":
        await state.update_data(without_broker="owner")
        text = "Тільки від власника"
    else:
        await state.update_data(without_broker=None)  # or just remove param
        text = "Усі оголошення"

    await callback_query.message.answer(f'Обрано: "{text}"')
    await show_advanced_options(callback_query.message, state)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "advanced_done", state="*")
async def advanced_done_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    summary = build_full_summary(user_data)  # We'll define build_full_summary below

    from aiogram.utils.markdown import escape_md
    summary_escaped = escape_md(summary)

    # A new keyboard that shows "Редагувати" or "Підписатися"
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("Редагувати", callback_data="edit_parameters"),
        InlineKeyboardButton("Підписатися", callback_data="subscribe"),
    )

    await callback_query.message.answer(summary_escaped, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_floor", state="*")
async def edit_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    floor_opts = user_data.get("floor_opts", {
        "not_first": False,
        "not_last": False,
        "floor_max_6": False,
        "floor_max_10": False,
        "floor_max_17": False,
        "only_last": False
    })
    await state.update_data(floor_opts=floor_opts)

    kb = floor_keyboard(floor_opts)
    await callback_query.message.answer("🏢 Налаштуйте поверх:", reply_markup=kb)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("toggle_floor_"), state="*")
async def toggle_floor_callback(callback_query: types.CallbackQuery, state: FSMContext):
    # e.g. toggle_floor_not_first, toggle_floor_only_last, toggle_floor_6 ...
    choice = callback_query.data.split("_", 2)[-1]  # "not_first", "not_last", "only_last", "6", "10", "17"
    user_data = await state.get_data()
    floor_opts = user_data.get("floor_opts", {
        "not_first": False,
        "not_last": False,
        "floor_max_6": False,
        "floor_max_10": False,
        "floor_max_17": False,
        "only_last": False
    })

    current_val = floor_opts.get(choice, False)
    new_val = not current_val
    floor_opts[choice] = new_val

    # Contradictions
    if choice == "only_last" and new_val is True:
        floor_opts["not_last"] = False
    if choice == "not_last" and new_val is True:
        floor_opts["only_last"] = False

    if choice in ["6", "10", "17"] and new_val is True:
        for other in ["6", "10", "17"]:
            if other != choice:
                floor_opts[f"floor_max_{other}"] = False

    await state.update_data(floor_opts=floor_opts)

    kb = floor_keyboard(floor_opts)  # ensure floor_keyboard also uses "not_first", "not_last", etc.

    try:
        await callback_query.message.edit_text(
            "🏢 Налаштуйте поверх:",
            reply_markup=kb
        )
    except MessageNotModified:
        await callback_query.answer("Немає змін.")

    await callback_query.answer()


def floor_opts_key(num_str):
    return f"floor_max_{num_str}"


@dp.callback_query_handler(lambda c: c.data == "floor_done", state="*")
async def floor_done_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    floor_opts = user_data.get("floor_opts", {})

    # Convert toggles to final fields
    # For example:
    #  - is_not_first_floor = "yes" if floor_opts["not_first"] else None
    #  - last_floor = "yes" if floor_opts["only_last"] else ("no" if floor_opts["not_last"] else None)
    #  - floor_max = 6 or 10 or 17 or None
    advanced_data = {}

    if floor_opts.get("not_first"):
        advanced_data["is_not_first_floor"] = "yes"
    else:
        advanced_data["is_not_first_floor"] = None

    if floor_opts.get("only_last"):
        advanced_data["last_floor"] = "yes"
    elif floor_opts.get("not_last"):
        advanced_data["last_floor"] = "no"
    else:
        advanced_data["last_floor"] = None

    if floor_opts.get("floor_max_6"):
        advanced_data["floor_max"] = 6
    elif floor_opts.get("floor_max_10"):
        advanced_data["floor_max"] = 10
    elif floor_opts.get("floor_max_17"):
        advanced_data["floor_max"] = 17
    else:
        advanced_data["floor_max"] = None

    # Save to state
    await state.update_data(**advanced_data)

    # Return to advanced menu or summary
    await callback_query.message.answer("💾 Зміни збережено.")
    # e.g. show advanced menu again
    # or show final summary

    # **Now** go back to the advanced options menu:
    await show_advanced_options(callback_query.message, state)

    await callback_query.answer()


async def show_advanced_options(message: types.Message, state: FSMContext):
    # Build a keyboard for advanced fields
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Поверх", callback_data="edit_floor"),
    )
    keyboard.add(
        InlineKeyboardButton("З тваринами?", callback_data="pets_allowed"),
    )
    keyboard.add(
        InlineKeyboardButton("Від власника?", callback_data="without_broker"),
    )
    # "Готово" -> return to summary
    keyboard.add(InlineKeyboardButton("Повернутись назад", callback_data="advanced_done"))

    await message.answer("Оберіть параметр для зміни:", reply_markup=keyboard)


def build_full_summary(data: dict) -> str:
    # property_type_apartment, property_type_house, property_type_room
    mapping_property = {"apartment": "Квартира", "house": "Будинок"}
    property_type = data.get("property_type", "")
    ua_lang_property_type = mapping_property.get(property_type, "")

    city = data.get("city", "")
    rooms = data.get("rooms", [])  # list
    price_min = data.get("price_min", "")
    price_max = data.get("price_max", "")
    logger.info('price_min: ')
    logger.info(price_min)
    logger.info('price_max: ')
    logger.info(price_max)

    floor_max = data.get("floor_max")
    is_not_first_floor = data.get("is_not_first_floor")
    last_floor = data.get("last_floor")
    pets_allowed_full = data.get("pets_allowed_full")
    without_broker = data.get("without_broker")

    # build lines
    lines = []
    lines.append(f"🏷 Тип нерухомості: {ua_lang_property_type}")
    lines.append(f"🏙️ Місто: {city}")
    lines.append(f"🛏️ Кількість кімнат: {', '.join(map(str, rooms)) if rooms else 'Не важливо'}")

    # Price range
    if price_min and price_max:
        price_range = f"від {price_min} до {price_max}"
        lines.append(f"💰 Ціновий діапазон: {price_range} грн")
    elif price_min and not price_max:
        lines.append(f"від {price_min} грн")
    elif price_max and not price_min:
        lines.append(f"до {price_max} грн")
    else:
        lines.append("💰 Ціна: не важливо")

    # ADVANCED
    if floor_max:
        lines.append(f"🏢 Поверхи до: {floor_max}")
    if is_not_first_floor == "yes":
        lines.append("🏢 Не перший поверх")
    elif is_not_first_floor == "no":
        lines.append("🏢 Перший поверх дозволено")

    if last_floor == "yes":
        lines.append("🏢 Тільки останній поверх")
    elif last_floor == "no":
        lines.append("🏢 Не останній поверх")

    if pets_allowed_full:
        lines.append("🐶🐈🐹 Дозволено з тваринами")

    if without_broker == "owner":
        lines.append("😎 Тільки від власника")

    return "**Поточні параметри пошуку**\n" + "\n".join(lines)


@dp.callback_query_handler(lambda c: c.data.startswith("view_photos:"))
async def handle_view_photos(callback_query: types.CallbackQuery):
    # Expect callback_data "view_photos:<resource_url>"
    _, resource_url = callback_query.data.split("view_photos:")
    # Retrieve the extra photos for this ad.
    # Implement get_extra_images(resource_url) that returns a list of URLs.
    extra_images = get_extra_images(resource_url)  # <-- You must implement this.
    if extra_images:
        media = MediaGroup()
        for i, url in enumerate(extra_images):
            if i == 0:
                media.attach_photo(url, caption="Додаткові фото:")
            else:
                media.attach_photo(url)
        await bot.send_media_group(chat_id=callback_query.from_user.id, media=media)
    else:
        await callback_query.answer("Немає додаткових фото.", show_alert=True)
