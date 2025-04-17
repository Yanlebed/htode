# services/telegram_service/app/handlers/favorites.py
import decimal
import logging

from aiogram import types
from aiogram.dispatcher import FSMContext

from common.utils.ad_utils import get_ad_images
from ..bot import dp, bot

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from common.config import build_ad_text
from common.db.models import add_favorite_ad, remove_favorite_ad, list_favorites, get_db_user_id_by_telegram_id, \
    get_full_ad_description
from common.db.database import execute_query
from ..utils.message_utils import safe_send_message, safe_send_photo, safe_answer_callback_query

logger = logging.getLogger(__name__)


@dp.callback_query_handler(lambda c: c.data.startswith("add_fav:"))
async def handle_add_fav(callback_query: types.CallbackQuery):
    try:
        # Get the part after "add_fav:"
        callback_data = callback_query.data.split("add_fav:")[1]

        # Check if it's a URL or an ID
        if callback_data.startswith("http"):
            resource_url = callback_data
            logger.info(f"Looking up ad ID for resource_url: {resource_url}")

            # Find the ad by its resource_url
            sql = "SELECT id FROM ads WHERE resource_url = %s"
            result = execute_query(sql, [resource_url], fetchone=True)

            if not result:
                logger.error(f"Ad not found for resource_url: {resource_url}")
                await callback_query.answer("Оголошення не знайдено.", show_alert=True)
                return

            ad_id = result["id"]
            logger.info(f"Found ad ID {ad_id} for resource_url: {resource_url}")
        else:
            # It's already an ID
            ad_id = int(callback_data)

        telegram_id = callback_query.from_user.id
        db_user_id = get_db_user_id_by_telegram_id(telegram_id)

        if not db_user_id:
            logger.error(f"User not found for telegram_id: {telegram_id}")
            await callback_query.answer("Помилка: Користувач не знайдений.", show_alert=True)
            return

        # Add to favorites
        add_favorite_ad(db_user_id, ad_id)

        # Get the existing reply markup
        reply_markup = callback_query.message.reply_markup

        # Find and replace the button
        new_markup = InlineKeyboardMarkup()
        for row in reply_markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data and button.callback_data.startswith("add_fav:"):
                    # Replace with "remove from favorites" button
                    new_row.append(InlineKeyboardButton(
                        "💚 Додано до обраних",
                        callback_data=f"rm_fav_from_ad:{ad_id}"
                    ))
                else:
                    new_row.append(button)
            new_markup.row(*new_row)

        # Update the message with new markup
        await callback_query.message.edit_reply_markup(reply_markup=new_markup)
        await callback_query.answer("Додано до обраних!")

    except ValueError as e:
        logger.error(f"Error parsing callback data: {e}")
        await callback_query.answer("Помилка при додаванні до обраних.", show_alert=True)
    except Exception as e:
        logger.exception(f"Unexpected error in handle_add_fav: {e}")
        await callback_query.answer("Сталася помилка.", show_alert=True)


@dp.callback_query_handler(lambda c: c.data.startswith("rm_fav_from_ad:"))
async def handle_rm_fav_from_ad(callback_query: types.CallbackQuery):
    try:
        # Get ad ID
        ad_id = int(callback_query.data.split("rm_fav_from_ad:")[1])

        telegram_id = callback_query.from_user.id
        db_user_id = get_db_user_id_by_telegram_id(telegram_id)

        # Remove from favorites
        remove_favorite_ad(db_user_id, ad_id)

        # Get the existing reply markup
        reply_markup = callback_query.message.reply_markup

        # Find and replace the button back to "Add to favorites"
        new_markup = InlineKeyboardMarkup()
        for row in reply_markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data and button.callback_data.startswith("rm_fav_from_ad:"):
                    # Replace with "add to favorites" button
                    new_row.append(InlineKeyboardButton(
                        "❤️ Додати в обрані",
                        callback_data=f"add_fav:{ad_id}"
                    ))
                else:
                    new_row.append(button)
            new_markup.row(*new_row)

        # Update the message with new markup
        await callback_query.message.edit_reply_markup(reply_markup=new_markup)
        await callback_query.answer("Видалено з обраних!")

    except Exception as e:
        logger.error(f"Error removing from favorites: {e}")
        await callback_query.answer("Помилка при видаленні з обраних.", show_alert=True)


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


@dp.message_handler(lambda msg: msg.text == "❤️ Обрані")
async def show_favorites_carousel(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    # Get all favorites
    favorites = list_favorites(db_user_id)

    if not favorites:
        await message.answer("У вас немає обраних оголошень.")
        return

    # Convert Decimal to float for JSON serialization
    serializable_favorites = []
    for fav in favorites:
        serializable_fav = {}
        for key, value in fav.items():
            if isinstance(value, decimal.Decimal):
                serializable_fav[key] = float(value)
            else:
                serializable_fav[key] = value
        serializable_favorites.append(serializable_fav)

    # Store favorites in state and set current index to 0
    await state.update_data(favorites=serializable_favorites, current_fav_index=0)

    # Show the first ad
    await show_favorite_at_index(message.chat.id, serializable_favorites, 0)


async def show_favorite_at_index(chat_id, favorites, index):
    """Helper function to show a favorite ad at a specific index"""
    if not favorites or index < 0 or index >= len(favorites):
        await safe_send_message(chat_id=chat_id, text="Помилка: Оголошення не знайдено.")
        return

    ad = favorites[index]
    ad_id = ad.get('ad_id')

    # Get all needed data for the ad
    sql = "SELECT * FROM ads WHERE id = %s"
    full_ad = execute_query(sql, [ad_id], fetchone=True)

    if not full_ad:
        await safe_send_message(chat_id=chat_id, text="Помилка: Оголошення не знайдено в базі даних.")
        return

    # Get image for the ad
    s3_image_url = get_ad_images(ad_id)[0] if get_ad_images(ad_id) else None

    # Build the text
    text = build_ad_text(full_ad)

    # Create navigation buttons
    kb = InlineKeyboardMarkup(row_width=2)

    # Add navigation buttons
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("◀️ Попереднє", callback_data=f"fav_prev:{index}"))

    if index < len(favorites) - 1:
        nav_row.append(InlineKeyboardButton("Наступне ▶️", callback_data=f"fav_next:{index}"))

    if nav_row:
        kb.row(*nav_row)

    # Add resource URL and other info
    resource_url = full_ad.get("resource_url")

    # Fetch image gallery URL
    sql_images = "SELECT image_url FROM ad_images WHERE ad_id = %s"
    rows_imgs = execute_query(sql_images, [ad_id], fetch=True)
    image_urls = [r["image_url"].strip() for r in rows_imgs] if rows_imgs else []
    if image_urls:
        image_str = ",".join(image_urls)
        gallery_url = f"https://f3cc-178-150-42-6.ngrok-free.app/gallery?images={image_str}"
    else:
        gallery_url = "https://f3cc-178-150-42-6.ngrok-free.app/gallery?images="

    # Fetch phone numbers
    sql_phones = "SELECT phone FROM ad_phones WHERE ad_id = %s"
    rows_phones = execute_query(sql_phones, [ad_id], fetch=True)
    phone_list = [row["phone"].replace("tel:", "").strip() for row in rows_phones] if rows_phones else []
    if phone_list:
        phone_str = ",".join(phone_list)
        phone_webapp_url = f"https://f3cc-178-150-42-6.ngrok-free.app/phones?numbers={phone_str}"
    else:
        phone_webapp_url = "https://f3cc-178-150-42-6.ngrok-free.app/phones?numbers="

    # Add action buttons
    kb.add(
        InlineKeyboardButton(
            text="🖼 Більше фото",
            web_app=WebAppInfo(url=gallery_url)
        ),
        InlineKeyboardButton(
            text="📲 Подзвонити",
            web_app=WebAppInfo(url=phone_webapp_url)
        )
    )
    kb.add(
        InlineKeyboardButton("💚 Видалити з обраних", callback_data=f"rm_fav_carousel:{ad_id}:{index}"),
        InlineKeyboardButton("ℹ️ Повний опис", callback_data=f"show_more_fav:{resource_url}")
    )

    # Send the message with photo
    if s3_image_url:
        await safe_send_photo(
            chat_id=chat_id,
            photo=s3_image_url,
            caption=text,
            parse_mode='Markdown',
            reply_markup=kb
        )
    else:
        await safe_send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=kb
        )


@dp.callback_query_handler(lambda c: c.data.startswith("fav_next:"))
async def handle_next_favorite(callback_query: types.CallbackQuery, state: FSMContext):
    current_index = int(callback_query.data.split(":")[1])
    user_data = await state.get_data()
    favorites = user_data.get('favorites', [])

    # Calculate next index
    next_index = current_index + 1
    if next_index >= len(favorites):
        next_index = 0  # Loop back to beginning

    # Update state
    await state.update_data(current_fav_index=next_index)

    # Delete the current message
    await callback_query.message.delete()

    # Show the next ad
    await show_favorite_at_index(callback_query.message.chat.id, favorites, next_index)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("fav_prev:"))
async def handle_prev_favorite(callback_query: types.CallbackQuery, state: FSMContext):
    current_index = int(callback_query.data.split(":")[1])
    user_data = await state.get_data()
    favorites = user_data.get('favorites', [])

    # Calculate previous index
    prev_index = current_index - 1
    if prev_index < 0:
        prev_index = len(favorites) - 1  # Loop back to end

    # Update state
    await state.update_data(current_fav_index=prev_index)

    # Delete the current message
    await callback_query.message.delete()

    # Show the previous ad
    await show_favorite_at_index(callback_query.message.chat.id, favorites, prev_index)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("rm_fav_carousel:"))
async def handle_rm_fav_carousel(callback_query: types.CallbackQuery, state: FSMContext):
    parts = callback_query.data.split(":")
    ad_id = int(parts[1])
    current_index = int(parts[2])

    telegram_id = callback_query.from_user.id
    db_user_id = get_db_user_id_by_telegram_id(telegram_id)

    # Remove from favorites in DB
    remove_favorite_ad(db_user_id, ad_id)

    # Update favorites list in state
    user_data = await state.get_data()
    favorites = user_data.get('favorites', [])
    favorites = [f for f in favorites if f.get('ad_id') != ad_id]

    if not favorites:
        # No more favorites
        await callback_query.message.delete()
        await callback_query.message.answer("У вас більше немає обраних оголошень.")
        await state.finish()
        await callback_query.answer("Видалено з обраних!")
        return

    # Adjust current index if needed
    if current_index >= len(favorites):
        current_index = len(favorites) - 1

    # Update state
    await state.update_data(favorites=favorites, current_fav_index=current_index)

    # Delete the current message
    await callback_query.message.delete()

    # Show the new current ad
    await show_favorite_at_index(callback_query.message.chat.id, favorites, current_index)
    await callback_query.answer("Видалено з обраних!")


@dp.callback_query_handler(lambda c: c.data.startswith("show_more_fav:"))
async def handle_show_more_fav(callback_query: types.CallbackQuery):
    # Extract the resource_url from the callback data
    try:
        _, resource_url = callback_query.data.split("show_more_fav:")
    except Exception:
        await safe_answer_callback_query(
            callback_query_id=callback_query.id,
            text="Невірні дані.",
            show_alert=True
        )
        return

    # Retrieve the full description
    full_description = get_full_ad_description(resource_url)
    if full_description:
        try:
            # Edit the original message's caption
            original_caption = callback_query.message.caption or ""
            new_caption = original_caption + "\n\n" + full_description

            try:
                await bot.edit_message_caption(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    caption=new_caption,
                    parse_mode='Markdown',
                    reply_markup=callback_query.message.reply_markup  # keep buttons
                )
                await safe_answer_callback_query(
                    callback_query_id=callback_query.id,
                    text="Повний опис показано!"
                )
            except Exception as e:
                logger.warning(f"Failed to edit caption: {e}. Sending as new message.")
                # If editing fails, send as a new message
                await safe_send_message(
                    chat_id=callback_query.from_user.id,
                    text=full_description
                )
                await safe_answer_callback_query(
                    callback_query_id=callback_query.id,
                    text="Повний опис надіслано окремим повідомленням!"
                )
        except Exception as e:
            logger.error(f"Failed to show full description: {e}")
            await safe_answer_callback_query(
                callback_query_id=callback_query.id,
                text="Помилка при отриманні опису.",
                show_alert=True
            )
    else:
        await safe_answer_callback_query(
            callback_query_id=callback_query.id,
            text="Немає додаткового опису.",
            show_alert=True
        )
