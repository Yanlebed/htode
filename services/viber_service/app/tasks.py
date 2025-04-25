# services/viber_service/app/tasks.py

import logging
import asyncio
from datetime import datetime
from viberbot import Api
from viberbot.api.messages import TextMessage, PictureMessage, KeyboardMessage

from common.celery_app import celery_app
from common.db.database import execute_query
from common.db.models import get_full_ad_description, get_db_user_id_by_telegram_id
from common.messaging.service import messaging_service
from .bot import viber

logger = logging.getLogger(__name__)


@celery_app.task(name='viber_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id):
    """
    Send an ad with extra buttons to a Viber user.
    Uses the unified messaging service for consistent handling across platforms.

    Args:
        user_id: User's Viber ID
        text: Ad description text
        s3_image_url: URL to the primary image
        resource_url: Original ad URL
        ad_id: Database ID of the ad
        ad_external_id: External ID of the ad
    """

    async def send():
        logger.info(f"Sending ad with extra buttons to Viber user {user_id}...")

        # Get DB user ID from Viber ID
        db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type="viber")
        if not db_user_id:
            logger.warning(f"No database user found for Viber ID {user_id}")
            return

        # Fetch images for the ad
        sql_images = "SELECT image_url FROM ad_images WHERE ad_id = %s"
        rows_imgs = execute_query(sql_images, [ad_id], fetch=True)
        image_urls = [r["image_url"].strip() for r in rows_imgs] if rows_imgs else []

        # Fetch phone numbers for the ad
        sql_phones = "SELECT phone FROM ad_phones WHERE ad_id = %s"
        rows_phones = execute_query(sql_phones, [ad_id], fetch=True)
        phone_list = [row["phone"].replace("tel:", "").strip() for row in rows_phones] if rows_phones else []

        # Prepare the ad data
        ad_data = {
            "id": ad_id,
            "external_id": ad_external_id,
            "resource_url": resource_url,
            "images": image_urls,
            "phones": phone_list,
            # Parse the text to extract other ad properties
            "price": int(text.split("Ціна: ")[1].split(" ")[0]) if "Ціна: " in text else 0,
            "city": text.split("Місто: ")[1].split("\n")[0] if "Місто: " in text else "",
            "address": text.split("Адреса: ")[1].split("\n")[0] if "Адреса: " in text else "",
            "rooms_count": text.split("Кіл-сть кімнат: ")[1].split("\n")[0] if "Кіл-сть кімнат: " in text else "",
            "square_feet": text.split("Площа: ")[1].split(" ")[0] if "Площа: " in text else "",
            "floor": text.split("Поверх: ")[1].split(" ")[0] if "Поверх: " in text else "",
            "total_floors": text.split("з ")[1].split("\n")[0] if "з " in text else ""
        }

        # Use the unified messaging service to send the ad
        success = await messaging_service.send_ad(
            user_id=db_user_id,
            ad_data=ad_data,
            image_url=s3_image_url
        )

        if success:
            logger.info(f"Successfully sent ad {ad_id} to Viber user {db_user_id}")
        else:
            logger.error(f"Failed to send ad {ad_id} to Viber user {db_user_id}")

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in Viber send_ad_with_extra_buttons: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='viber_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """
    Send subscription-related notifications to Viber users.
    Uses the unified messaging service for consistent handling across platforms.

    Args:
        user_id: Database user ID
        notification_type: Type of notification (payment_success, expiration_reminder, etc.)
        data: Dictionary with notification data
    """

    async def send():
        try:
            # Prepare message content
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
                    f"Ваша підписка закінчується через {data['days_left']} "
                    f"{'день' if data['days_left'] == 1 else 'дні' if data['days_left'] < 5 else 'днів'}.\n"
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

            # Send notification using the unified messaging service
            success = await messaging_service.send_notification(
                user_id=user_id,
                text=message_text
            )

            if not success:
                logger.error(f"Failed to send notification to Viber user {user_id}")

        except Exception as e:
            logger.error(f"Error in Viber send_subscription_notification: {e}")

    # Run the async function
    try:
        asyncio.run(send())
    except RuntimeError as e:
        logger.warning(f"RuntimeError in Viber send_subscription_notification: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='viber_service.app.tasks.check_expired_conversations')
def check_expired_conversations():
    """
    Check for expired Viber conversations and clean up.
    Viber conversations expire after 24 hours, so we need to handle this.
    """
    logger.info("Checking for expired Viber conversations")

    try:
        # Get users with Viber IDs who were active in the last 24-28 hours
        sql = """
              SELECT id, viber_id, last_active
              FROM users
              WHERE viber_id IS NOT NULL
                AND last_active > NOW() - interval '28 hours'
                AND last_active \
                  < NOW() - interval '24 hours'
              """
        users = execute_query(sql, fetch=True)

        for user in users:
            user_id = user["id"]
            viber_id = user["viber_id"]

            logger.info(f"Marking Viber conversation as expired for user {user_id} (Viber ID: {viber_id})")

            # Update the last_conversation_expired flag
            update_sql = """
                         UPDATE users
                         SET viber_conversation_expired = TRUE
                         WHERE id = %s
                         """
            execute_query(update_sql, [user_id])

            # Optionally send a reminder message via another channel if available
            try:
                # Check if user has other messaging channels
                check_sql = """
                            SELECT telegram_id, whatsapp_id
                            FROM users
                            WHERE id = %s \
                              AND (telegram_id IS NOT NULL OR whatsapp_id IS NOT NULL) \
                            """
                other_channels = execute_query(check_sql, [user_id], fetchone=True)

                if other_channels:
                    reminder_text = (
                        "Ваша Viber сесія закінчилася. Щоб продовжити отримувати сповіщення через Viber, "
                        "будь ласка, напишіть будь-яке повідомлення нашому боту."
                    )

                    asyncio.run(messaging_service.send_notification(
                        user_id=user_id,
                        text=reminder_text
                    ))
            except Exception as channel_err:
                logger.error(f"Error sending channel reminder: {channel_err}")

    except Exception as e:
        logger.error(f"Error checking expired Viber conversations: {e}")