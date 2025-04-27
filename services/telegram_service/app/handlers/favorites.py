# services/telegram_service/app/handlers/favorites.py
import decimal
import logging

from aiogram import types
from aiogram.dispatcher import FSMContext

from common.db.session import db_session
from common.db.repositories.ad_repository import AdRepository
from common.db.repositories.favorite_repository import FavoriteRepository
from common.db.repositories.user_repository import UserRepository
from common.utils.ad_utils import get_ad_images
from common.utils.cache_managers import FavoriteCacheManager, AdCacheManager
from common.utils.cache_invalidation import get_entity_cache_key

from ..bot import dp, bot

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from common.config import build_ad_text
from ..utils.message_utils import safe_send_message, safe_send_photo, safe_answer_callback_query

logger = logging.getLogger(__name__)


@dp.callback_query_handler(lambda c: c.data.startswith("add_fav:"))
async def handle_add_fav(callback_query: types.CallbackQuery):
    try:
        # Get the part after "add_fav:"
        callback_data = callback_query.data.split("add_fav:")[1]

        # Database user ID
        telegram_id = callback_query.from_user.id

        with db_session() as db:
            db_user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")

            if not db_user:
                logger.error(f"User not found for telegram_id: {telegram_id}")
                await callback_query.answer("Помилка: Користувач не знайдений.", show_alert=True)
                return

            db_user_id = db_user.id

            # Parse ad ID
            if callback_data.startswith("http"):
                # It's a URL, find ad by resource_url
                resource_url = callback_data
                ad = AdRepository.get_by_resource_url(db, resource_url)

                if not ad:
                    logger.error(f"Ad not found for resource_url: {resource_url}")
                    await callback_query.answer("Оголошення не знайдено.", show_alert=True)
                    return

                ad_id = ad.id
            else:
                # It's already an ID
                ad_id = int(callback_data)

            # Add to favorites using a repository
            try:
                favorite = FavoriteRepository.add_favorite(db, db_user_id, ad_id)
            except ValueError as e:
                # This happens when a user already has 50 favorites
                await callback_query.answer(str(e), show_alert=True)
                return

            if not favorite:
                await callback_query.answer("Помилка при додаванні до обраних.", show_alert=True)
                return

            # Invalidate favorite cache for this user
            FavoriteCacheManager.invalidate_all(db_user_id)

        # Update UI to show the "Added to favorites" button
        # Get the existing reply markup
        reply_markup = callback_query.message.reply_markup

        # Find and replace the button
        new_markup = InlineKeyboardMarkup()
        for row in reply_markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data and button.callback_data.startswith("add_fav:"):
                    # Replace it with the "remove from favorites" button
                    new_row.append(InlineKeyboardButton(
                        "💚 Додано до обраних",
                        callback_data=f"rm_fav_from_ad:{ad_id}"
                    ))
                else:
                    new_row.append(button)
            new_markup.row(*new_row)

        # Update the message with a new markup
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

        with db_session() as db:
            # Get database user ID
            db_user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
            if not db_user:
                await callback_query.answer("Користувач не знайдений.", show_alert=True)
                return

            db_user_id = db_user.id

            # Remove from favorites using repository
            success = FavoriteRepository.remove_favorite(db, db_user_id, ad_id)

            if not success:
                await callback_query.answer("Не вдалося видалити з обраних.", show_alert=True)
                return

            # Invalidate favorite cache for this user
            FavoriteCacheManager.invalidate_all(db_user_id)

        # Get the existing reply markup
        reply_markup = callback_query.message.reply_markup

        # Find and replace the button back to "Add to favorites"
        new_markup = InlineKeyboardMarkup()
        for row in reply_markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data and button.callback_data.startswith("rm_fav_from_ad:"):
                    # Replace it with the "add to favorites" button
                    new_row.append(InlineKeyboardButton(
                        "❤️ Додати в обрані",
                        callback_data=f"add_fav:{ad_id}"
                    ))
                else:
                    new_row.append(button)
            new_markup.row(*new_row)

        # Update the message with a new markup
        await callback_query.message.edit_reply_markup(reply_markup=new_markup)
        await callback_query.answer("Видалено з обраних!")

    except Exception as e:
        logger.error(f"Error removing from favorites: {e}")
        await callback_query.answer("Помилка при видаленні з обраних.", show_alert=True)


@dp.message_handler(lambda msg: msg.text == "Мої обрані")
async def show_favorites(message: types.Message):
    telegram_id = message.from_user.id

    with db_session() as db:
        # Get database user ID
        db_user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
        if not db_user:
            await message.answer("Користувач не знайдений.")
            return

        db_user_id = db_user.id

        # Try to get favorites from the cache first
        cached_favorites = FavoriteCacheManager.get_user_favorites(db_user_id)

        if cached_favorites:
            favs = cached_favorites
        else:
            # Not in cache, get from a repository
            favs = FavoriteRepository.list_favorites(db, db_user_id)
            # Cache is updated in the repository

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
    telegram_id = callback_query.from_user.id

    with db_session() as db:
        # Get database user ID
        db_user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
        if not db_user:
            await callback_query.answer("Користувач не знайдений.", show_alert=True)
            return

        db_user_id = db_user.id

        # Remove favorite using repository
        success = FavoriteRepository.remove_favorite(db, db_user_id, ad_id)

        if not success:
            await callback_query.answer("Не вдалося видалити з обраних.", show_alert=True)
            return

        # Invalidate favorites cache for this user
        FavoriteCacheManager.invalidate_all(db_user_id)

    await callback_query.answer("Видалено з обраних.")


@dp.message_handler(lambda msg: msg.text == "❤️ Обрані")
async def show_favorites_carousel(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id

    with db_session() as db:
        # Get database user ID
        db_user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
        if not db_user:
            await message.answer("Користувач не знайдений.")
            return

        db_user_id = db_user.id

        # Try to get favorites from cache first
        cached_favorites = FavoriteCacheManager.get_user_favorites(db_user_id)

        if cached_favorites:
            favorites = cached_favorites
        else:
            # Not in cache, get from repository
            favorites = FavoriteRepository.list_favorites(db, db_user_id)
            # Cache is updated in the repository

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

    # Get all necessary data for the ad using a repository pattern
    with db_session() as db:
        # Try to get from the cache first
        full_ad = AdCacheManager.get_full_ad_data(ad_id)

        if not full_ad:
            # Not in cache, get from a repository
            full_ad = AdRepository.get_full_ad_data(db, ad_id)
            # AdRepository handles caching

    if not full_ad:
        await safe_send_message(chat_id=chat_id, text="Помилка: Оголошення не знайдено в базі даних.")
        return

    # Get image for the ad
    image_urls = get_ad_images(ad_id)
    s3_image_url = image_urls[0] if image_urls else None

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

    # Get image gallery URLs
    gallery_images = get_ad_images(ad_id)
    if gallery_images:
        image_str = ",".join(gallery_images)
        gallery_url = f"https://f3cc-178-150-42-6.ngrok-free.app/gallery?images={image_str}"
    else:
        gallery_url = "https://f3cc-178-150-42-6.ngrok-free.app/gallery?images="

    # Get phone numbers
    with db_session() as db:
        phones = AdRepository.get_ad_phones(db, ad_id)
        phone_list = [phone["phone"] for phone in phones if phone["phone"]]

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

    # Send the message with a photo
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
        next_index = 0  # Loop back to the beginning

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

    with db_session() as db:
        # Get database user ID
        db_user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
        if not db_user:
            await callback_query.answer("Користувач не знайдений.", show_alert=True)
            return

        db_user_id = db_user.id

        # Remove from favorites using repository
        success = FavoriteRepository.remove_favorite(db, db_user_id, ad_id)

        if not success:
            await callback_query.answer("Не вдалося видалити з обраних.", show_alert=True)
            return

        # Invalidate favorite cache for this user
        FavoriteCacheManager.invalidate_all(db_user_id)

    # Update favorite list in state
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

    # Adjust the current index if needed
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

    # Retrieve the full description using repository
    with db_session() as db:
        # Try cache first
        cache_key = get_entity_cache_key("ad_description", resource_url)
        full_description = AdCacheManager.get(cache_key)

        if not full_description:
            # Not in cache, get from a repository
            full_description = AdRepository.get_description_by_resource_url(db, resource_url)

            # Cache if found
            if full_description:
                AdCacheManager.set(cache_key, full_description, 3600)  # Cache for 1 hour

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