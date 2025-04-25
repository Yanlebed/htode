# services/telegram_service/app/tasks.py
import datetime
import asyncio
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MediaGroup, CallbackQuery, WebAppInfo
from common.celery_app import celery_app
from .bot import bot, dp
from common.db.database import execute_query
from common.db.models import get_full_ad_description, get_db_user_id_by_telegram_id
from .utils.message_utils import (
    safe_send_photo, safe_send_message,
    safe_answer_callback_query, safe_edit_message
)
from common.messaging.service import messaging_service

logger = logging.getLogger(__name__)


@celery_app.task(name='telegram_service.app.tasks.send_subscription_reminders')
def send_subscription_reminders():
    """
    Checks for subscriptions expiring in 2 days, 1 day, or today,
    and sends a reminder message.
    """
    now = datetime.datetime.utcnow()
    # We'll define intervals
    # 2 days left means subscription_until = now + 2 days
    # Let's do something like:

    sql = """
          SELECT id, telegram_id, subscription_until
          FROM users
          WHERE subscription_until IS NOT NULL
            AND subscription_until > NOW() -- subscription is still active
            AND subscription_until < NOW() + interval '3 days'; \
          """
    # We'll refine the logic in Python to see if it's exactly 2 days, 1 day, or same day.

    rows = execute_query(sql, fetch=True)
    for row in rows:
        telegram_id = row['telegram_id']
        sub_end = row['subscription_until']  # datetime
        days_left = (sub_end - now).days

        if days_left == 2:
            text = "Нагадування: Ваш безкоштовний період закінчується через 2 дні!"
        elif days_left == 1:
            text = "Нагадування: Завтра закінчується безкоштовний період!"
        elif days_left == 0:
            text = "Нагадування: Сьогодні закінчується підписка!"
        else:
            # Not exactly 2,1,0 => skip
            continue

        # Send message using our safe utility
        async def send_msg(chat_id, txt):
            await safe_send_message(chat_id, txt)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If no event loop is set, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(send_msg(telegram_id, text))


@celery_app.task(name='telegram_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id):
    """
    Send an ad with extra buttons to a user.
    Using the unified messaging service for consistent handling across platforms.

    Args:
        user_id: User's platform-specific ID (telegram_id, viber_id, or whatsapp_id)
        text: Ad description text
        s3_image_url: URL to the primary image
        resource_url: Original ad URL
        ad_id: Database ID of the ad
        ad_external_id: External ID of the ad
    """
    import asyncio

    async def send():
        logger.info(f"Sending ad with extra buttons to user {user_id}...")

        # Get DB user ID from platform-specific ID
        db_user_id = get_db_user_id_by_telegram_id(user_id)
        if not db_user_id:
            logger.warning(f"No database user found for ID {user_id}")
            return

        # Fetch images for the ad
        from common.db.database import execute_query
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
        # This will automatically handle formatting for each platform
        success = await messaging_service.send_ad(
            user_id=db_user_id,
            ad_data=ad_data,
            image_url=s3_image_url
        )

        if success:
            logger.info(f"Successfully sent ad {ad_id} to user {db_user_id}")
        else:
            logger.error(f"Failed to send ad {ad_id} to user {db_user_id}")

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_ad_with_extra_buttons: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@dp.callback_query_handler(lambda c: c.data.startswith("show_more:"))
async def handle_show_more(callback_query: CallbackQuery):
    # Extract the resource_url from the callback data
    try:
        _, resource_url = callback_query.data.split("show_more:")
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
            # Option 1: Edit the original message's caption using our safe utility
            original_caption = callback_query.message.caption or ""
            new_caption = original_caption + "\n\n" + full_description

            # Instead of directly using bot.edit_message_caption
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
                # Option 2: If editing fails, send as a new message
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


@celery_app.task(name='telegram_service.app.tasks.check_expiring_subscriptions')
def check_expiring_subscriptions():
    """
    Check for subscriptions that will expire soon and send reminders.
    Uses the unified messaging service for consistent handling across platforms.
    """
    try:
        # Check for subscriptions expiring in 3, 2, and 1 days
        for days in [3, 2, 1]:
            # Find users whose subscription expires in exactly `days` days
            from common.db.database import execute_query

            sql = """
                  SELECT id, subscription_until
                  FROM users
                  WHERE subscription_until IS NOT NULL
                    AND subscription_until > NOW()
                    AND subscription_until < NOW() + interval '%s days 1 hour'
                    AND subscription_until \
                      > NOW() + interval '%s days'
                  """
            users = execute_query(sql, [days, days - 1], fetch=True)

            for user in users:
                user_id = user["id"]
                end_date = user["subscription_until"].strftime("%d.%m.%Y")

                # Send notification using the task
                celery_app.send_task(
                    'telegram_service.app.tasks.send_subscription_notification',
                    args=[
                        user_id,
                        "expiration_reminder",
                        {
                            "days_left": days,
                            "subscription_until": end_date
                        }
                    ]
                )

        # Also notify on the day of expiration
        sql_today = """
                    SELECT id, subscription_until
                    FROM users
                    WHERE subscription_until IS NOT NULL
                      AND DATE (subscription_until) = CURRENT_DATE
                    """
        today_users = execute_query(sql_today, fetch=True)

        for user in today_users:
            user_id = user["id"]
            end_date = user["subscription_until"].strftime("%d.%m.%Y %H:%M")

            # Send notification using the task
            celery_app.send_task(
                'telegram_service.app.tasks.send_subscription_notification',
                args=[
                    user_id,
                    "expiration_today",
                    {"subscription_until": end_date}
                ]
            )

    except Exception as e:
        logger.error(f"Error checking expiring subscriptions: {e}")


@celery_app.task(name='telegram_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """
    Send subscription-related notifications to users.
    Uses the unified messaging service for consistent handling across platforms.

    Args:
        user_id: Database user ID
        notification_type: Type of notification (payment_success, expiration_reminder, etc.)
        data: Dictionary with notification data
    """
    import asyncio

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
                logger.error(f"Failed to send notification to user {user_id}")

        except Exception as e:
            logger.error(f"Error in send_subscription_notification: {e}")

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
