# services/whatsapp_service/app/tasks.py

import logging
import asyncio
from datetime import datetime

from common.celery_app import celery_app
from common.db.database import execute_query
from common.db.models import get_full_ad_description, get_db_user_id_by_telegram_id
from common.messaging.service import messaging_service
from .bot import client, TWILIO_PHONE_NUMBER

logger = logging.getLogger(__name__)


@celery_app.task(name='whatsapp_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id):
    """
    Send an ad with instructions for interaction via WhatsApp.
    Uses the unified messaging service for consistent handling across platforms.

    Args:
        user_id: WhatsApp number
        text: Ad description text
        s3_image_url: URL to the primary image
        resource_url: Original ad URL
        ad_id: Database ID of the ad
        ad_external_id: External ID of the ad
    """

    async def send():
        logger.info(f"Sending ad to WhatsApp user {user_id}...")

        # Get DB user ID from WhatsApp number
        db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type="whatsapp")
        if not db_user_id:
            logger.warning(f"No database user found for WhatsApp ID {user_id}")
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
            logger.info(f"Successfully sent ad {ad_id} to WhatsApp user {db_user_id}")
        else:
            logger.error(f"Failed to send ad {ad_id} to WhatsApp user {db_user_id}")

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in WhatsApp send_ad_with_extra_buttons: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='whatsapp_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """
    Send subscription-related notifications to WhatsApp users.
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
                logger.error(f"Failed to send notification to WhatsApp user {user_id}")

        except Exception as e:
            logger.error(f"Error in WhatsApp send_subscription_notification: {e}")

    # Run the async function
    try:
        asyncio.run(send())
    except RuntimeError as e:
        logger.warning(f"RuntimeError in WhatsApp send_subscription_notification: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='whatsapp_service.app.tasks.check_template_status')
def check_template_status():
    """
    Check the status of WhatsApp message templates.
    WhatsApp Business API requires templates for certain types of messages.
    """
    logger.info("Checking WhatsApp template status")

    try:
        # Use Twilio client to check template status
        templates = client.messaging.services(TWILIO_PHONE_NUMBER.split(":")[1]).message_templates.list()

        for template in templates:
            logger.info(f"Template {template.sid}: Status={template.status}")

            # Log rejected templates for review
            if template.status == 'rejected':
                logger.warning(f"Template {template.sid} rejected: {template.reason}")

                # Notify admins about rejected templates
                admin_notification_sql = """
                                         SELECT id \
                                         FROM users \
                                         WHERE is_admin = TRUE LIMIT 1
                                         """
                admin = execute_query(admin_notification_sql, fetchone=True)

                if admin:
                    admin_id = admin["id"]
                    notification_text = (
                        f"⚠️ WhatsApp template {template.sid} was rejected\n"
                        f"Reason: {template.reason}\n\n"
                        "Please review and update the template."
                    )

                    # Send notification to admin
                    asyncio.run(messaging_service.send_notification(
                        user_id=admin_id,
                        text=notification_text
                    ))

    except Exception as e:
        logger.error(f"Error checking WhatsApp template status: {e}")


@celery_app.task(name='whatsapp_service.app.tasks.process_media_messages')
def process_media_messages():
    """
    Process and store media messages sent by users.
    WhatsApp media messages have a 30-day retention period in Twilio.
    """
    logger.info("Processing WhatsApp media messages")

    try:
        # Get recent unprocessed media messages
        sql = """
              SELECT id, whatsapp_id, media_url, processed
              FROM whatsapp_media_messages
              WHERE processed = FALSE
              ORDER BY created_at DESC LIMIT 50
              """
        media_messages = execute_query(sql, fetch=True)

        for message in media_messages:
            message_id = message["id"]
            media_url = message["media_url"]

            logger.info(f"Processing media message {message_id} with URL {media_url}")

            # Download and store the media to a more permanent location
            try:
                # Import your S3 upload utility
                from common.utils.s3_utils import _upload_image_to_s3

                # Generate a unique ID for the media
                unique_id = f"whatsapp_media_{message_id}"

                # Upload to S3
                s3_url = _upload_image_to_s3(media_url, unique_id, max_retries=3)

                if s3_url:
                    # Update the record with the permanent URL
                    update_sql = """
                                 UPDATE whatsapp_media_messages
                                 SET permanent_url = %s, \
                                     processed     = TRUE
                                 WHERE id = %s
                                 """
                    execute_query(update_sql, [s3_url, message_id])
                    logger.info(f"Successfully processed media message {message_id}")
                else:
                    logger.warning(f"Failed to upload media for message {message_id}")

            except Exception as media_err:
                logger.error(f"Error processing media message {message_id}: {media_err}")

    except Exception as e:
        logger.error(f"Error in process_media_messages: {e}")