# common/messaging/tasks.py

import logging
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

from common.celery_app import celery_app
from common.db.database import execute_query
from common.db.models import get_platform_ids_for_user, get_db_user_id_by_telegram_id, get_full_ad_description
from common.utils.ad_utils import get_ad_images
from .service import messaging_service
from .handlers.support_handler import handle_support_command, handle_support_category, SUPPORT_CATEGORIES

logger = logging.getLogger(__name__)


@celery_app.task(name='common.messaging.tasks.send_notification')
def send_notification(user_id: int, text: str, **kwargs):
    """
    Send a notification to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        text: Notification text
        **kwargs: Additional parameters for the notification
    """

    async def send():
        try:
            # Use the messaging service to send the notification
            success = await messaging_service.send_notification(
                user_id=user_id,
                text=text,
                **kwargs
            )

            if not success:
                logger.error(f"Failed to send notification to user {user_id}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_notification: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.tasks.send_ad')
def send_ad(user_id: int, ad_data: Dict[str, Any], image_url: Optional[str] = None, **kwargs):
    """
    Send an ad to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        ad_data: Dictionary with ad data
        image_url: Optional URL for the primary ad image
        **kwargs: Additional parameters for the ad
    """

    async def send():
        try:
            # Use the messaging service to send the ad
            success = await messaging_service.send_ad(
                user_id=user_id,
                ad_data=ad_data,
                image_url=image_url,
                **kwargs
            )

            if not success:
                logger.error(f"Failed to send ad to user {user_id}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error sending ad to user {user_id}: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_ad: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.tasks.send_menu')
def send_menu(user_id: int, text: str, options: List[Dict[str, str]], **kwargs):
    """
    Send a menu with options to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        text: Menu title/description text
        options: List of option dictionaries with at least 'text' and 'value' keys
        **kwargs: Additional parameters for the menu
    """

    async def send():
        try:
            # Get the platform-specific messenger
            platform, platform_id, messenger = await messaging_service.get_messenger_for_user(user_id)

            if not platform or not platform_id or not messenger:
                logger.error(f"No messaging platform found for user {user_id}")
                return False

            # Format user ID for the platform
            formatted_id = await messenger.format_user_id(platform_id)

            # Send the menu
            await messenger.send_menu(
                user_id=formatted_id,
                text=text,
                options=options,
                **kwargs
            )

            return True
        except Exception as e:
            logger.error(f"Error sending menu to user {user_id}: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_menu: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.tasks.send_cross_platform_message')
def send_cross_platform_message(user_id: int, text: str, platforms: Optional[List[str]] = None, **kwargs):
    """
    Send a message to a user across multiple platforms.

    Args:
        user_id: Database user ID
        text: Message text
        platforms: Optional list of platforms to target (e.g., ["telegram", "viber"])
                  If None, will send to all available platforms for the user
        **kwargs: Additional parameters for the message
    """

    async def send():
        try:
            # Get all platform IDs for the user
            platform_ids = get_platform_ids_for_user(user_id)

            if not platform_ids:
                logger.error(f"No platform IDs found for user {user_id}")
                return False

            # Determine which platforms to send to
            target_platforms = platforms or ["telegram", "viber", "whatsapp"]
            sent_count = 0

            # Send to each platform that the user has an ID for
            for platform in target_platforms:
                platform_id_key = f"{platform}_id"
                if platform_ids.get(platform_id_key):
                    platform_id = platform_ids[platform_id_key]

                    # Get the messenger for this platform
                    messenger = messaging_service.get_messenger(platform)
                    if not messenger:
                        logger.warning(f"No messenger available for platform {platform}")
                        continue

                    # Format the user ID
                    formatted_id = await messenger.format_user_id(str(platform_id))

                    # Send the message
                    try:
                        await messenger.send_text(
                            user_id=formatted_id,
                            text=text,
                            **kwargs
                        )
                        sent_count += 1
                    except Exception as e:
                        logger.error(f"Error sending to {platform}: {e}")

            return sent_count > 0
        except Exception as e:
            logger.error(f"Error in send_cross_platform_message for user {user_id}: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_cross_platform_message: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


# --- New Consolidated Tasks ---

@celery_app.task(name='common.messaging.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id, platform=None):
    """
    Consolidated task to send an ad with platform-specific buttons.
    Can be called directly with a platform-specific ID or database user ID.

    Args:
        user_id: User's platform-specific ID or database user ID
        text: Ad description text
        s3_image_url: URL to the primary image
        resource_url: Original ad URL
        ad_id: Database ID of the ad
        ad_external_id: External ID of the ad
        platform: Optional platform override if user_id is platform-specific
    """

    async def send():
        logger.info(f"Sending ad with extra buttons to user {user_id}...")

        # Determine if this is a database user ID or platform-specific ID
        db_user_id = None
        if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
            # This is likely a database user ID
            db_user_id = int(user_id)
        elif platform:
            # We have a platform-specific ID and we know the platform
            db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type=platform)
        else:
            # Try to detect platform from ID format
            if user_id.startswith("whatsapp:"):
                db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type="whatsapp")
            elif len(user_id) > 20:  # Viber IDs are typically long UUIDs
                db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type="viber")
            else:
                # Default to Telegram for shorter IDs
                db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type="telegram")

        if not db_user_id:
            logger.warning(f"No database user found for user ID {user_id}")
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


@celery_app.task(name='common.messaging.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """
    Consolidated task to send subscription-related notifications across platforms.

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
                logger.error(f"Failed to send notification to user {user_id}")

            return success

        except Exception as e:
            logger.error(f"Error in send_subscription_notification: {e}")
            return False

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


@celery_app.task(name='common.messaging.tasks.check_expiring_subscriptions')
def check_expiring_subscriptions():
    """
    Consolidated task to check for expiring subscriptions and send reminders.
    Replaces duplicate implementations across platform-specific modules.
    """
    try:
        # Check for subscriptions expiring in 3, 2, and 1 days
        for days in [3, 2, 1]:
            # Find users whose subscription expires in exactly `days` days
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

                # Send notification using the consolidated task
                send_subscription_notification.delay(
                    user_id,
                    "expiration_reminder",
                    {
                        "days_left": days,
                        "subscription_until": end_date
                    }
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

            # Send notification using the consolidated task
            send_subscription_notification.delay(
                user_id,
                "expiration_today",
                {"subscription_until": end_date}
            )

        return {"status": "success", "users_notified": len(users) + len(today_users)}

    except Exception as e:
        logger.error(f"Error checking expiring subscriptions: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task(name='common.messaging.tasks.process_show_more_description')
def process_show_more_description(user_id, resource_url, message_id=None, platform=None):
    """
    Consolidated task to handle "show more" functionality across platforms.

    Args:
        user_id: User's platform-specific ID or database user ID
        resource_url: URL of the ad to get description for
        message_id: Optional message ID (for platforms that support editing)
        platform: Optional platform identifier
    """

    async def process():
        try:
            # Get the full description
            full_description = get_full_ad_description(resource_url)
            if not full_description:
                logger.warning(f"No description found for resource {resource_url}")
                return False

            # Use the platform_utils to resolve user ID and platform info
            from common.messaging.platform_utils import resolve_user_id, get_messenger_instance

            # Get database user ID, platform and platform-specific ID
            db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)

            # If we have a database user ID, try to use the unified messaging service
            if db_user_id:
                try:
                    success = await messaging_service.send_notification(
                        user_id=db_user_id,
                        text=full_description
                    )
                    if success:
                        return True
                except Exception as e:
                    logger.warning(f"Error using messaging service for DB user {db_user_id}: {e}")

            # If no success with unified service, try platform-specific approach
            if platform_name and platform_id:
                # For Telegram and if we have a message_id, try to edit the message
                if platform_name == "telegram" and message_id:
                    try:
                        from common.messaging.utils import safe_edit_message_telegram
                        from services.telegram_service.app.bot import bot

                        # Try to get the original message
                        message = await bot.get_message(
                            chat_id=platform_id,
                            message_id=message_id
                        )
                        original_content = message.caption or message.text or ""

                        # Add the full description to the original content
                        new_content = original_content + "\n\n" + full_description

                        # Try to edit the message
                        await safe_edit_message_telegram(
                            chat_id=platform_id,
                            message_id=message_id,
                            text=new_content,
                            parse_mode='Markdown',
                            reply_markup=message.reply_markup
                        )
                        return True
                    except Exception as e:
                        logger.warning(f"Failed to edit Telegram message: {e}, falling back to new message")

                # If editing failed or not applicable, send as a new message
                # Get the messenger instance
                messenger = get_messenger_instance(platform_name)
                if messenger:
                    # Format the user ID
                    from common.messaging.platform_utils import format_user_id_for_platform
                    formatted_id = format_user_id_for_platform(platform_id, platform_name)

                    # Send the message
                    await messenger.send_text(
                        user_id=formatted_id,
                        text=full_description
                    )
                    return True

            # If we couldn't resolve the user ID or platform, use safe_send_message
            # which will try its best to determine the right approach
            from common.messaging.utils import safe_send_message
            success = await safe_send_message(
                user_id=user_id,
                text=full_description,
                platform=platform
            )

            return success

        except Exception as e:
            logger.error(f"Error processing show more description: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(process())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in process_show_more_description: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(process())
        finally:
            loop.close()


# --- Support-Related Tasks ---

@celery_app.task(name='common.messaging.tasks.start_support_conversation')
def start_support_conversation(user_id, platform=None):
    """
    Start a support conversation with a user.
    Works with any platform (telegram, viber, whatsapp).

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier
    """

    async def execute():
        try:
            # Call the unified handler
            success = await handle_support_command(user_id, platform)
            return {"success": success}
        except Exception as e:
            logger.error(f"Error starting support conversation: {e}")
            return {"success": False, "error": str(e)}

    # Run the async function
    try:
        return asyncio.run(execute())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in start_support_conversation: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(execute())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.tasks.process_support_category')
def process_support_category(user_id, category, platform=None):
    """
    Process a selected support category.
    Works with any platform (telegram, viber, whatsapp).

    Args:
        user_id: User's platform-specific ID or database ID
        category: Selected support category
        platform: Optional platform identifier
    """

    async def execute():
        try:
            # Call the unified handler
            success = await handle_support_category(user_id, category, platform)
            return {"success": success}
        except Exception as e:
            logger.error(f"Error processing support category: {e}")
            return {"success": False, "error": str(e)}

    # Run the async function
    try:
        return asyncio.run(execute())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in process_support_category: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(execute())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.tasks.forward_to_support')
def forward_to_support(user_id, message, category, platform=None):
    """
    Forward a user message to the support system.

    Args:
        user_id: User's platform-specific ID or database ID
        message: User's message to forward
        category: Support category for context
        platform: Optional platform identifier
    """

    async def execute():
        try:
            # Get user information for context
            db_user_id = None
            if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
                db_user_id = int(user_id)
            elif platform:
                db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type=platform)

            if not db_user_id:
                logger.warning(f"Could not resolve database user ID for {user_id}")

            # Get platform information
            platform_ids = get_platform_ids_for_user(db_user_id) if db_user_id else {}

            # Prepare data for the support system
            support_data = {
                "user_id": db_user_id,
                "message": message,
                "category": category,
                "platform": platform,
                "platform_ids": platform_ids,
                "timestamp": datetime.now().isoformat()
            }

            # Store in database or send to support system
            # This is just a placeholder - implement your actual support system integration
            logger.info(f"Support request received: {support_data}")

            # Return success
            return {"success": True, "support_ticket_id": str(uuid.uuid4())}
        except Exception as e:
            logger.error(f"Error forwarding to support: {e}")
            return {"success": False, "error": str(e)}

    # Run the async function
    try:
        return asyncio.run(execute())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in forward_to_support: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(execute())
        finally:
            loop.close()


# Helper function to get the template for a support category
def get_support_template(category, lang='uk'):
    """
    Get the template message for a support category.

    Args:
        category: Support category (payment, technical, other)
        lang: Language code ('uk' for Ukrainian, 'en' for English)

    Returns:
        Template message string
    """
    category_data = SUPPORT_CATEGORIES.get(category, SUPPORT_CATEGORIES['other'])
    return category_data['template']