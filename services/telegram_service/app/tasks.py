# services/telegram_service/app/tasks.py
import datetime
import asyncio
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MediaGroup, CallbackQuery, WebAppInfo
from common.celery_app import celery_app
from .bot import bot, dp
from common.db.database import execute_query
from common.db.models import get_full_ad_description

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
      AND subscription_until < NOW() + interval '3 days'; 
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

        # Send message
        # You can use async with run_coroutine_threadsafe or a simple approach:
        # But here let's do a simple approach with "asyncio.run"
        # or direct aiogram call in the worker if we have set up a shared event loop properly.
        # For simplicity:

        async def send_msg(chat_id, txt):
            await bot.send_message(chat_id, txt)

        loop = asyncio.get_event_loop()
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
            InlineKeyboardButton("❤️ Додати в обрані", callback_data=f"add_fav:{ad_url}"),
            InlineKeyboardButton("ℹ️ Повний опис", callback_data=f"show_more:{ad_url}")
        )

        #### 4) Send the message with the final keyboard
        try:
            await bot.send_photo(
                chat_id=user_id_number,
                photo=image_url,
                caption=message_text,
                parse_mode='Markdown',
                reply_markup=kb
            )
        except Exception as e:
            logger.error(f"Failed to send ad with extra buttons to user {user_id_number}: {e}")

    return asyncio.run(send(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id))



@dp.callback_query_handler(lambda c: c.data.startswith("show_more:"))
async def handle_show_more(callback_query: CallbackQuery):
    # Extract the resource_url from the callback data
    try:
        _, resource_url = callback_query.data.split("show_more:")
    except Exception:
        await callback_query.answer("Невірні дані.", show_alert=True)
        return

    # Retrieve the full description.
    # Implement a helper that looks up the ad record from your DB
    # or, if the ad page itself contains the full description, request and parse it.
    full_description = get_full_ad_description(resource_url)  # IMPLEMENT THIS!
    if full_description:
        try:
            # Option 1: Edit the original message's caption (if the caption can be edited)
            original_caption = callback_query.message.caption or ""
            new_caption = original_caption + "\n\n" + full_description
            await bot.edit_message_caption(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                caption=new_caption,
                parse_mode='Markdown',
                reply_markup=callback_query.message.reply_markup  # keep buttons
            )
            await callback_query.answer("Повний опис показано!")
        except Exception as e:
            # Option 2: Send a new message with the full description.
            await bot.send_message(callback_query.from_user.id, full_description)
            await callback_query.answer("Повний опис надіслано окремим повідомленням!")
    else:
        await callback_query.answer("Немає додаткового опису.", show_alert=True)
