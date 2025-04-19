# services/telegram_service/app/tasks.py
import datetime
import asyncio
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MediaGroup, CallbackQuery, WebAppInfo
from common.celery_app import celery_app
from .bot import bot, dp
from common.db.database import execute_query
from common.db.models import get_full_ad_description
from .utils.message_utils import (
    safe_send_photo, safe_send_message,
    safe_answer_callback_query, safe_edit_message
)

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


@celery_app.task(name="telegram_service.app.tasks.send_ad_with_extra_buttons")
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id):
    async def send(user_id_number, message_text, image_url, ad_url, adv_id, adv_external_id):
        logger.info(f"Sending ad with extra buttons to user {user_id_number}... adv_id-{adv_id}")

        #### 1) Fetch all images for "Більше фото" as before...
        sql_images = "SELECT image_url FROM ad_images WHERE ad_id = %s"
        rows_imgs = execute_query(sql_images, [adv_id], fetch=True)
        image_urls = [r["image_url"].strip() for r in rows_imgs] if rows_imgs else []
        if image_urls:
            image_str = ",".join(image_urls)
            gallery_url = f"https://f3cc-178-150-42-6.ngrok-free.app/gallery?images={image_str}"
        else:
            gallery_url = "https://f3cc-178-150-42-6.ngrok-free.app/gallery?images="

        #### 2) Fetch phone numbers for "Подзвонити"
        sql_phones = "SELECT phone FROM ad_phones WHERE ad_id = %s"
        rows_phones = execute_query(sql_phones, [adv_id], fetch=True)
        phone_list = [row["phone"].replace("tel:", "").strip() for row in rows_phones] if rows_phones else []
        if phone_list:
            phone_str = ",".join(phone_list)
            phone_webapp_url = f"https://f3cc-178-150-42-6.ngrok-free.app/phones?numbers={phone_str}"
        else:
            phone_webapp_url = "https://f3cc-178-150-42-6.ngrok-free.app/phones?numbers="

        #### 3) Build the inline keyboard with immediate Web Apps
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(
                text="🖼 Більше фото",
                web_app=WebAppInfo(url=gallery_url)
            ),
            InlineKeyboardButton(
                text="📲 Подзвонити",
                web_app=WebAppInfo(url=phone_webapp_url)
            ),
            InlineKeyboardButton("❤️ Додати в обрані", callback_data=f"add_fav:{adv_id}"),
            InlineKeyboardButton("ℹ️ Повний опис", callback_data=f"show_more:{ad_url}")
        )

        #### 4) Send the message with the final keyboard
        # Use safe_send_photo instead of bot.send_photo
        try:
            await safe_send_photo(
                chat_id=user_id_number,
                photo=image_url,
                caption=message_text,
                parse_mode='Markdown',
                reply_markup=kb,
                retry_count=3
            )
        except Exception as e:
            logger.error(f"Failed to send ad with extra buttons to user {user_id_number}: {e}")

    try:
        return asyncio.run(send(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id))
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_ad_with_extra_buttons: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id))
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
    """Check for subscriptions that will expire soon and send reminders"""
    try:
        # Check for subscriptions expiring in 3, 2, and 1 days
        for days in [3, 2, 1]:
            # Find users whose subscription expires in exactly `days` days
            sql = """
                  SELECT id, telegram_id, subscription_until
                  FROM users
                  WHERE subscription_until IS NOT NULL
                    AND subscription_until > NOW()
                    AND subscription_until < NOW() + interval '%s days 1 hour'
                    AND subscription_until \
                      > NOW() + interval '%s days' \
                  """
            users = execute_query(sql, [days, days - 1], fetch=True)

            for user in users:
                telegram_id = user["telegram_id"]
                end_date = user["subscription_until"].strftime("%d.%m.%Y")

                # Send notification
                celery_app.send_task(
                    'telegram_service.app.tasks.send_subscription_notification',
                    args=[
                        telegram_id,
                        "expiration_reminder",
                        {
                            "days_left": days,
                            "subscription_until": end_date
                        }
                    ]
                )

        # Also notify on the day of expiration
        sql_today = """
                    SELECT id, telegram_id, subscription_until
                    FROM users
                    WHERE subscription_until IS NOT NULL
                      AND DATE (subscription_until) = CURRENT_DATE \
                    """
        today_users = execute_query(sql_today, fetch=True)

        for user in today_users:
            telegram_id = user["telegram_id"]
            end_date = user["subscription_until"].strftime("%d.%m.%Y %H:%M")

            # Send notification
            celery_app.send_task(
                'telegram_service.app.tasks.send_subscription_notification',
                args=[
                    telegram_id,
                    "expiration_today",
                    {"subscription_until": end_date}
                ]
            )

    except Exception as e:
        logger.error(f"Error checking expiring subscriptions: {e}")


@celery_app.task(name='telegram_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """Send subscription-related notifications to users"""
    try:
        # Get messenger type and ID
        from common.messaging.service import MessagingService
        from common.messaging.telegram import TelegramMessenger
        from common.messaging.viber import ViberMessenger
        from common.messaging.whatsapp import WhatsAppMessenger
        from services.telegram_service.app.bot import bot
        from services.viber_service.app.bot import viber
        from services.whatsapp_service.app.bot import client as twilio_client

        messaging_service = MessagingService(
            TelegramMessenger(bot),
            ViberMessenger(viber),
            WhatsAppMessenger(twilio_client)
        )

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

        # Send notification via messaging service
        success = messaging_service.send_notification(user_id, message_text)

        if not success:
            logger.error(f"Failed to send notification to user {user_id}")

    except Exception as e:
        logger.error(f"Error in send_subscription_notification: {e}")
