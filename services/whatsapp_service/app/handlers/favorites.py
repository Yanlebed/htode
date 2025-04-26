# services/whatsapp_service/app/handlers/favorites.py

import logging
from ..utils.message_utils import safe_send_message, safe_send_media
from common.db.models import list_favorites, get_db_user_id_by_telegram_id, remove_favorite_ad, get_full_ad_description

logger = logging.getLogger(__name__)


async def show_favorites(user_id):
    """Show user's favorite listings"""
    # Get user's database ID
    db_user_id = get_db_user_id_by_telegram_id(user_id)

    if not db_user_id:
        await safe_send_message(user_id, "Помилка: Не вдалося знайти ваш профіль.")
        return

    # Get favorites
    favorites = list_favorites(db_user_id)

    if not favorites:
        await safe_send_message(user_id, "У вас немає обраних оголошень.")
        return

    # Store favorites in user state
    from ..bot import update_user_state
    await update_user_state(user_id, {
        "favorites": favorites,
        "current_favorite_index": 0
    })

    # Show the first favorite
    await show_favorite_at_index(user_id, 0)


async def show_favorite_at_index(user_id, index):
    """Display a favorite ad at the specified index"""
    from ..bot import get_user_state
    user_data = await get_user_state(user_id)
    favorites = user_data.get("favorites", [])

    if not favorites or index < 0 or index >= len(favorites):
        await safe_send_message(user_id, "Оголошення не знайдено.")
        return

    # Get current favorite
    favorite = favorites[index]

    # Format the ad information
    from common.config import GEO_ID_MAPPING
    city_name = GEO_ID_MAPPING.get(favorite.get('city'))

    message = (
        f"*Оголошення {index + 1} з {len(favorites)}*\n\n"
        f"💰 Ціна: {int(favorite.get('price'))} грн.\n"
        f"🏙️ Місто: {city_name}\n"
        f"📍 Адреса: {favorite.get('address')}\n"
        f"🛏️ Кількість кімнат: {favorite.get('rooms_count')}\n"
        f"📐 Площа: {favorite.get('square_feet')} кв.м.\n"
        f"🏢 Поверх: {favorite.get('floor')} з {favorite.get('total_floors')}\n\n"
        "Доступні дії:\n"
        "- 'Наступне' для перегляду наступного оголошення\n"
        "- 'Попереднє' для перегляду попереднього оголошення\n"
        "- 'Повний опис' для отримання детальної інформації\n"
        "- 'Видалити' щоб видалити з обраних\n"
        "- 'Меню' щоб повернутися до головного меню"
    )

    # Get image for the ad
    from common.utils.ad_utils import get_ad_images
    images = get_ad_images(favorite.get('ad_id'))

    if images:
        # Send the first image with the ad description
        await safe_send_media(user_id, images[0], message)
    else:
        # Send just the text if no images
        await safe_send_message(user_id, message)


async def handle_favorite_command(user_id, command):
    """Handle commands for favorites navigation"""
    from ..bot import get_user_state, update_user_state
    user_data = await get_user_state(user_id)
    current_index = user_data.get("current_favorite_index", 0)
    favorites = user_data.get("favorites", [])

    if not favorites:
        await safe_send_message(user_id, "У вас немає обраних оголошень.")
        return

    command_lower = command.lower().strip()

    if command_lower in ["next", "наступне", "след", "далі"]:
        # Move to next favorite
        next_index = current_index + 1
        if next_index >= len(favorites):
            next_index = 0  # Wrap around to beginning

        await update_user_state(user_id, {"current_favorite_index": next_index})
        await show_favorite_at_index(user_id, next_index)

    elif command_lower in ["previous", "попереднє", "назад", "пред"]:
        # Move to previous favorite
        prev_index = current_index - 1
        if prev_index < 0:
            prev_index = len(favorites) - 1  # Wrap around to end

        await update_user_state(user_id, {"current_favorite_index": prev_index})
        await show_favorite_at_index(user_id, prev_index)

    elif command_lower in ["delete", "видалити", "remove"]:
        # Remove the current favorite
        db_user_id = get_db_user_id_by_telegram_id(user_id)
        favorite = favorites[current_index]
        ad_id = favorite.get('ad_id')

        if remove_favorite_ad(db_user_id, ad_id):
            await safe_send_message(user_id, "Оголошення видалено з обраних.")

            # Update the favorites list
            favorites.pop(current_index)

            # Adjust current index if needed
            if not favorites:
                await update_user_state(user_id, {
                    "favorites": [],
                    "current_favorite_index": 0
                })
                await safe_send_message(user_id, "У вас більше немає обраних оголошень.")
                return
            elif current_index >= len(favorites):
                current_index = len(favorites) - 1

            await update_user_state(user_id, {
                "favorites": favorites,
                "current_favorite_index": current_index
            })
            await show_favorite_at_index(user_id, current_index)
        else:
            await safe_send_message(user_id, "Не вдалося видалити оголошення.")

    elif command_lower in ["description", "повний опис", "опис", "детальніше"]:
        # Show full description
        favorite = favorites[current_index]
        resource_url = favorite.get('resource_url')

        if resource_url:
            full_description = get_full_ad_description(resource_url)
            if full_description:
                await safe_send_message(user_id, f"*Повний опис:*\n\n{full_description}")
            else:
                await safe_send_message(user_id, "Детальний опис недоступний.")
        else:
            await safe_send_message(user_id, "Неможливо отримати опис для цього оголошення.")

    elif command_lower in ["menu", "меню", "назад до меню", "головне меню"]:
        # Return to main menu
        from .basic_handlers import handle_menu_command
        await handle_menu_command(user_id)

    else:
        # Unknown command
        await safe_send_message(
            user_id,
            "Невідома команда. Доступні дії:\n"
            "- 'Наступне'\n"
            "- 'Попереднє'\n"
            "- 'Повний опис'\n"
            "- 'Видалити'\n"
            "- 'Меню'"
        )