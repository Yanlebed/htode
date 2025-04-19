# services/viber_service/app/tasks.py

import logging
import asyncio
from common.celery_app import celery_app
from .bot import viber, state_manager
from .utils.message_utils import safe_send_message, safe_send_picture
from common.db.models import get_full_ad_data, get_full_ad_description
from common.utils.ad_utils import get_ad_images

logger = logging.getLogger(__name__)


@celery_app.task(name='viber_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id):
    """
    Send an ad with interactive buttons via Viber.

    Args:
        user_id: Viber user ID
        text: Ad description text
        s3_image_url: URL to the primary image
        resource_url: Original ad URL
        ad_id: Database ID of the ad
        ad_external_id: External ID of the ad
    """

    async def send():
        try:
            logger.info(f"Sending ad with extra buttons to Viber user {user_id}")

            # Create a keyboard for the ad
            keyboard = {
                "Type": "keyboard",
                "Buttons": [
                    {
                        "Columns": 3,
                        "Rows": 1,
                        "Text": "🖼 Більше фото",
                        "ActionType": "reply",
                        "ActionBody": f"more_photos:{ad_id}"
                    },
                    {
                        "Columns": 3,
                        "Rows": 1,
                        "Text": "📲 Подзвонити",
                        "ActionType": "reply",
                        "ActionBody": f"call_contact:{ad_id}"
                    },
                    {
                        "Columns": 3,
                        "Rows": 1,
                        "Text": "❤️ Додати в обрані",
                        "ActionType": "reply",
                        "ActionBody": f"add_fav:{ad_id}"
                    },
                    {
                        "Columns": 3,
                        "Rows": 1,
                        "Text": "ℹ️ Повний опис",
                        "ActionType": "reply",
                        "ActionBody": f"show_more:{resource_url}"
                    }
                ]
            }

            # Send the ad
            if s3_image_url:
                await safe_send_picture(user_id, s3_image_url, caption=text, keyboard=keyboard)
            else:
                await safe_send_message(user_id, text, keyboard=keyboard)

        except Exception as e:
            logger.error(f"Error sending ad to Viber user {user_id}: {e}")

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


@celery_app.task(name='viber_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """
    Send subscription-related notifications to Viber users.

    Args:
        user_id: Viber user ID
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

            # Send notification
            await safe_send_message(user_id, message_text)

        except Exception as e:
            logger.error(f"Error sending notification to Viber user {user_id}: {e}")

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