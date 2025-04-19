# services/whatsapp_service/app/tasks.py

import logging
import asyncio
from common.celery_app import celery_app
from .bot import client, TWILIO_PHONE_NUMBER, state_manager
from .utils.message_utils import safe_send_message, safe_send_media
from common.db.models import (
    get_full_ad_data,
    get_full_ad_description,
    get_db_user_id_by_telegram_id,
    add_favorite_ad,
    remove_favorite_ad,
    list_favorites
)
from common.utils.ad_utils import get_ad_images

logger = logging.getLogger(__name__)


@celery_app.task(name='whatsapp_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id):
    """
    Send an ad with instructions for interaction via WhatsApp.

    Args:
        user_id: WhatsApp user ID (phone number)
        text: Ad description text
        s3_image_url: URL to the primary image
        resource_url: Original ad URL
        ad_id: Database ID of the ad
        ad_external_id: External ID of the ad
    """

    async def send():
        try:
            logger.info(f"Sending ad to WhatsApp user {user_id}")

            # WhatsApp doesn't support rich buttons, so we'll add instructions to the text
            text_with_instructions = (
                f"{text}\n\n"
                "Доступні дії:\n"
                f"- Відповідь 'фото {ad_id}' для більше фото\n"
                f"- Відповідь 'тел {ad_id}' для номерів телефону\n"
                f"- Відповідь 'обр {ad_id}' щоб додати в обрані\n"
                f"- Відповідь 'опис {ad_id}' для повного опису"
            )

            # Ensure proper WhatsApp formatting - this is the corrected part
            formatted_user_id = user_id
            if not str(formatted_user_id).startswith("whatsapp:"):
                formatted_user_id = f"whatsapp:{formatted_user_id}"

            # Send the ad
            if s3_image_url:
                await safe_send_media(formatted_user_id, s3_image_url, caption=text_with_instructions)
            else:
                await safe_send_message(formatted_user_id, text_with_instructions)

        except Exception as e:
            logger.error(f"Error sending ad to WhatsApp user {user_id}: {e}")

    # Run the async function
    try:
        asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_ad_with_extra_buttons: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='whatsapp_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """
    Send subscription-related notifications to WhatsApp users.

    Args:
        user_id: WhatsApp user ID (phone number)
        notification_type: Type of notification (e.g., "payment_success", "expiration_reminder")
        data: Dictionary with notification data
    """

    async def send():
        try:
            # Prepare message content based on notification type
            if notification_type == "payment_success":
                message_text = (
                    f"✅ Оплату успішно отримано!\n\n"
                    f"🧾 Замовлення: {data['order_id']}\n"
                    f"💰 Сума: {data['amount']} грн.\n"
                    f"📅 Ваша підписка дійсна до: {data['subscription_until']}\n\n"
                    f"Дякуємо за підтримку нашого сервісу! 🙏"
                )
            elif notification_type == "expiration_reminder":
                message_text = (
                    f"⚠️ Нагадування про підписку\n\n"
                    f"Ваша підписка закінчується через {data['days_left']} {'день' if data['days_left'] == 1 else 'дні' if data['days_left'] < 5 else 'днів'}.\n"
                    f"Дата закінчення: {data['subscription_until']}\n\n"
                    f"Щоб продовжити користуватися сервісом, оновіть підписку."
                )
            elif notification_type == "expiration_today":
                message_text = (
                    f"⚠️ Ваша підписка закінчується сьогодні!\n\n"
                    f"Час закінчення: {data['subscription_until']}\n\n"
                    f"Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                )
            else:
                message_text = "Системне повідомлення."

            # Ensure proper WhatsApp formatting
            if not user_id.startswith("whatsapp:"):
                user_id = f"whatsapp:{user_id}"

            # Send notification
            await safe_send_message(user_id, message_text)

        except Exception as e:
            logger.error(f"Error sending notification to WhatsApp user {user_id}: {e}")

    # Run the async function
    try:
        asyncio.run(send())
    except RuntimeError as e:
        logger.warning(f"RuntimeError in send_subscription_notification: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='whatsapp_service.app.tasks.handle_favorite_actions')
def handle_favorite_actions(user_id, ad_id, action_type):
    """
    Handle favorite-related actions for WhatsApp users.

    Args:
        user_id: WhatsApp user ID (phone number)
        ad_id: ID of the ad
        action_type: Type of action (add, remove, view)
    """

    async def process():
        try:
            # Get user DB ID
            db_user_id = get_db_user_id_by_telegram_id(user_id)
            if not db_user_id:
                await safe_send_message(
                    user_id,
                    "Помилка: Не вдалося знайти ваш профіль користувача."
                )
                return

            # Handle different actions
            if action_type == "add":
                # Add ad to favorites
                try:
                    add_favorite_ad(db_user_id, ad_id)
                    await safe_send_message(
                        user_id,
                        "✅ Оголошення додано до обраних!"
                    )
                except ValueError as e:
                    await safe_send_message(user_id, f"Помилка: {str(e)}")

            elif action_type == "remove":
                # Remove ad from favorites
                remove_favorite_ad(db_user_id, ad_id)
                await safe_send_message(
                    user_id,
                    "✅ Оголошення видалено з обраних."
                )

            elif action_type == "view":
                # Get more details about the ad
                ad_data = get_full_ad_data(ad_id)
                if not ad_data:
                    await safe_send_message(
                        user_id,
                        "❌ Оголошення не знайдено."
                    )
                    return

                # Get images
                images = ad_data.get("images", [])
                if images and len(images) > 0:
                    # Send first image with information
                    from common.config import build_ad_text
                    text = build_ad_text(ad_data)
                    await safe_send_media(user_id, images[0], caption=text)

                    # Send additional images (up to 3)
                    for img_url in images[1:4]:  # Limit to 3 additional images
                        await safe_send_media(user_id, img_url)
                else:
                    # No images, just send text
                    from common.config import build_ad_text
                    text = build_ad_text(ad_data)
                    await safe_send_message(user_id, text)

        except Exception as e:
            logger.error(f"Error processing favorite action for user {user_id}: {e}")
            await safe_send_message(
                user_id,
                "❌ Сталася помилка при обробці запиту. Спробуйте ще раз."
            )

    # Run the async function
    try:
        asyncio.run(process())
    except RuntimeError as e:
        logger.warning(f"RuntimeError in handle_favorite_actions: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process())
        finally:
            loop.close()


@celery_app.task(name='whatsapp_service.app.tasks.show_more_photos')
def show_more_photos(user_id, ad_id):
    """
    Send additional photos for an ad to a WhatsApp user.

    Args:
        user_id: WhatsApp user ID
        ad_id: ID of the ad
    """

    async def process():
        try:
            # Get ad images from the database
            images = get_ad_images(ad_id)

            if not images or len(images) == 0:
                await safe_send_message(
                    user_id,
                    "❌ Для цього оголошення немає додаткових фотографій."
                )
                return

            # Send a message about the number of photos
            await safe_send_message(
                user_id,
                f"📸 Фотографії оголошення ({len(images)}):"
            )

            # Send images (limit to 5 to avoid spam)
            for img_url in images[:5]:
                await safe_send_media(user_id, img_url)

            # If there are more images, inform the user
            if len(images) > 5:
                await safe_send_message(
                    user_id,
                    f"... і ще {len(images) - 5} фотографій"
                )

        except Exception as e:
            logger.error(f"Error sending photos for ad {ad_id} to user {user_id}: {e}")
            await safe_send_message(
                user_id,
                "❌ Сталася помилка при завантаженні фотографій."
            )

    # Run the async function
    try:
        asyncio.run(process())
    except RuntimeError as e:
        logger.warning(f"RuntimeError in show_more_photos: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process())
        finally:
            loop.close()


@celery_app.task(name='whatsapp_service.app.tasks.show_phone_numbers')
def show_phone_numbers(user_id, ad_id):
    """
    Send phone numbers for an ad to a WhatsApp user.

    Args:
        user_id: WhatsApp user ID
        ad_id: ID of the ad
    """

    async def process():
        try:
            # Get ad data from database
            ad_data = get_full_ad_data(ad_id)

            if not ad_data:
                await safe_send_message(
                    user_id,
                    "❌ Оголошення не знайдено."
                )
                return

            # Get phone numbers
            phones = ad_data.get("phones", [])
            viber_link = ad_data.get("viber_link")

            if not phones and not viber_link:
                await safe_send_message(
                    user_id,
                    "❌ Для цього оголошення немає контактних даних."
                )
                return

            # Format phone numbers message
            message = "📞 Контактні дані:\n\n"

            if phones:
                for i, phone in enumerate(phones, 1):
                    # Clean phone number format
                    clean_phone = phone.replace("tel:", "").strip()
                    message += f"{i}. {clean_phone}\n"

            if viber_link:
                message += f"\nViber: {viber_link}"

            await safe_send_message(user_id, message)

        except Exception as e:
            logger.error(f"Error sending phone numbers for ad {ad_id} to user {user_id}: {e}")
            await safe_send_message(
                user_id,
                "❌ Сталася помилка при отриманні контактних даних."
            )

    # Run the async function
    try:
        asyncio.run(process())
    except RuntimeError as e:
        logger.warning(f"RuntimeError in show_phone_numbers: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process())
        finally:
            loop.close()


@celery_app.task(name='whatsapp_service.app.tasks.show_full_description')
def show_full_description(user_id, ad_id):
    """
    Send full description for an ad to a WhatsApp user.

    Args:
        user_id: WhatsApp user ID
        ad_id: ID of the ad
    """

    async def process():
        try:
            # Get ad data from database
            ad_data = get_full_ad_data(ad_id)

            if not ad_data:
                await safe_send_message(
                    user_id,
                    "❌ Оголошення не знайдено."
                )
                return

            # Get resource URL
            resource_url = ad_data.get("resource_url")

            if not resource_url:
                await safe_send_message(
                    user_id,
                    "❌ Неможливо отримати опис для цього оголошення."
                )
                return

            # Get full description
            description = get_full_ad_description(resource_url)

            if description:
                await safe_send_message(
                    user_id,
                    f"📝 Повний опис оголошення:\n\n{description}"
                )
            else:
                await safe_send_message(
                    user_id,
                    "❌ Повний опис недоступний."
                )

        except Exception as e:
            logger.error(f"Error sending full description for ad {ad_id} to user {user_id}: {e}")
            await safe_send_message(
                user_id,
                "❌ Сталася помилка при отриманні опису."
            )

    # Run the async function
    try:
        asyncio.run(process())
    except RuntimeError as e:
        logger.warning(f"RuntimeError in show_full_description: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process())
        finally:
            loop.close()


@celery_app.task(name='whatsapp_service.app.tasks.show_favorites')
def show_favorites(user_id, page=0):
    """
    Show user's favorite listings with pagination.

    Args:
        user_id: WhatsApp user ID
        page: Page number (starting from 0)
    """

    async def process():
        try:
            # Get user DB ID
            db_user_id = get_db_user_id_by_telegram_id(user_id)

            if not db_user_id:
                await safe_send_message(
                    user_id,
                    "Помилка: Не вдалося знайти ваш профіль користувача."
                )
                return

            # Get favorites with pagination (5 per page)
            favorites = list_favorites(db_user_id)

            if not favorites:
                await safe_send_message(
                    user_id,
                    "У вас немає обраних оголошень."
                )
                return

            # Calculate pagination
            per_page = 5
            total_pages = (len(favorites) - 1) // per_page + 1
            start_idx = page * per_page
            end_idx = min(start_idx + per_page, len(favorites))
            current_favorites = favorites[start_idx:end_idx]

            # Send header with pagination info
            await safe_send_message(
                user_id,
                f"📑 Ваші обрані оголошення (сторінка {page + 1} з {total_pages}):"
            )

            # Send each favorite as a separate message
            for i, favorite in enumerate(current_favorites, start=start_idx + 1):
                from common.config import build_ad_text

                # Build ad text
                text = build_ad_text(favorite)
                text += f"\n\n#{i} з {len(favorites)}"

                # Add instructions
                text += (
                    f"\n\nДоступні дії:\n"
                    f"- Відповідь 'видалити {favorite['ad_id']}' для видалення з обраних\n"
                    f"- Відповідь 'фото {favorite['ad_id']}' для більше фото\n"
                    f"- Відповідь 'тел {favorite['ad_id']}' для номерів телефону\n"
                    f"- Відповідь 'опис {favorite['ad_id']}' для повного опису"
                )

                # Get image
                image_urls = get_ad_images(favorite['ad_id'])

                if image_urls:
                    await safe_send_media(user_id, image_urls[0], caption=text)
                else:
                    await safe_send_message(user_id, text)

            # Send pagination controls if needed
            if total_pages > 1:
                pagination_text = "Для перегляду інших сторінок введіть:\n"

                if page > 0:
                    pagination_text += f"- 'обрані {page}' для попередньої сторінки\n"

                if page < total_pages - 1:
                    pagination_text += f"- 'обрані {page + 2}' для наступної сторінки\n"

                await safe_send_message(user_id, pagination_text)

        except Exception as e:
            logger.error(f"Error showing favorites for user {user_id}: {e}")
            await safe_send_message(
                user_id,
                "❌ Сталася помилка при завантаженні обраних оголошень."
            )

    # Run the async function
    try:
        asyncio.run(process())
    except RuntimeError as e:
        logger.warning(f"RuntimeError in show_favorites: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process())
        finally:
            loop.close()