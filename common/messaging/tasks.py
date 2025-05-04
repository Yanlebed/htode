# common/messaging/tasks.py

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Union

from sqlalchemy import func

from common.celery_app import celery_app
from common.db.operations import get_platform_ids_for_user, get_db_user_id_by_telegram_id, get_full_ad_description, Ad
from .service import messaging_service
from .handlers.support_handler import handle_support_command, handle_support_category, SUPPORT_CATEGORIES
from common.db.repositories.user_repository import UserRepository
from common.db.session import db_session
from ..db.models import User
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the messaging logger
from . import logger


@celery_app.task(name='common.messaging.tasks.send_notification')
@log_operation("send_notification")
def send_notification(user_id: int, text: str, **kwargs):
    """
    Send a notification to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        text: Notification text
        **kwargs: Additional parameters for the notification
    """
    with log_context(logger, user_id=user_id, text_length=len(text)):
        async def send():
            try:
                # Use the messaging service to send the notification
                success = await messaging_service.send_notification(
                    user_id=user_id,
                    text=text,
                    **kwargs
                )

                if not success:
                    logger.error(f"Failed to send notification", extra={
                        'user_id': user_id,
                        'text_preview': text[:50]
                    })
                    return False

                logger.info("Notification sent successfully", extra={
                    'user_id': user_id,
                    'text_length': len(text)
                })
                return True
            except Exception as e:
                logger.error(f"Error sending notification", exc_info=True, extra={
                    'user_id': user_id,
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_notification", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.send_ad')
@log_operation("send_ad")
def send_ad(user_id: int, ad_data: Dict[str, Any], image_url: Optional[str] = None, **kwargs):
    """
    Send an ad to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        ad_data: Dictionary with ad data
        image_url: Optional URL for the primary ad image
        **kwargs: Additional parameters for the ad
    """
    with log_context(logger, user_id=user_id, ad_id=ad_data.get('id')):
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
                    logger.error(f"Failed to send ad", extra={
                        'user_id': user_id,
                        'ad_id': ad_data.get('id')
                    })
                    return False

                logger.info("Ad sent successfully", extra={
                    'user_id': user_id,
                    'ad_id': ad_data.get('id'),
                    'has_image': bool(image_url)
                })
                return True
            except Exception as e:
                logger.error(f"Error sending ad", exc_info=True, extra={
                    'user_id': user_id,
                    'ad_id': ad_data.get('id'),
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_ad", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.send_menu')
@log_operation("send_menu")
def send_menu(user_id: int, text: str, options: List[Dict[str, str]], **kwargs):
    """
    Send a menu with options to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        text: Menu title/description text
        options: List of option dictionaries with at least 'text' and 'value' keys
        **kwargs: Additional parameters for the menu
    """
    with log_context(logger, user_id=user_id, options_count=len(options)):
        async def send():
            try:
                # Get the platform-specific messenger
                platform, platform_id, messenger = await messaging_service.get_messenger_for_user(user_id)

                if not platform or not platform_id or not messenger:
                    logger.error(f"No messaging platform found", extra={'user_id': user_id})
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

                logger.info("Menu sent successfully", extra={
                    'user_id': user_id,
                    'platform': platform,
                    'options_count': len(options)
                })
                return True
            except Exception as e:
                logger.error(f"Error sending menu", exc_info=True, extra={
                    'user_id': user_id,
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_menu", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.send_cross_platform_message')
@log_operation("send_cross_platform_message")
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
    with log_context(logger, user_id=user_id, platforms=platforms, text_length=len(text)):
        async def send():
            aggregator = LogAggregator(logger, f"send_cross_platform_{user_id}")

            try:
                # Get all platform IDs for the user
                platform_ids = get_platform_ids_for_user(user_id)

                if not platform_ids:
                    logger.error(f"No platform IDs found", extra={'user_id': user_id})
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
                            logger.warning(f"No messenger available", extra={'platform': platform})
                            aggregator.add_error("No messenger", {'platform': platform})
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
                            aggregator.add_item({'platform': platform}, success=True)
                        except Exception as e:
                            logger.error(f"Error sending to platform", exc_info=True, extra={
                                'platform': platform,
                                'error_type': type(e).__name__
                            })
                            aggregator.add_error(str(e), {'platform': platform})

                aggregator.log_summary()

                logger.info("Cross-platform message sending completed", extra={
                    'user_id': user_id,
                    'sent_count': sent_count,
                    'total_platforms': len(target_platforms)
                })
                return sent_count > 0
            except Exception as e:
                logger.error(f"Error in send_cross_platform_message", exc_info=True, extra={
                    'user_id': user_id,
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_cross_platform_message", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


# --- New Consolidated Tasks ---

@celery_app.task(name='common.messaging.tasks.send_ad_with_extra_buttons')
@log_operation("send_ad_with_extra_buttons")
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
    with log_context(logger, user_id=user_id, ad_id=ad_id, platform=platform):
        async def send():
            logger.info(f"Sending ad with extra buttons", extra={
                'user_id': user_id,
                'ad_id': ad_id,
                'platform': platform
            })

            # Determine if this is a database user ID or platform-specific ID
            db_user_id = None
            if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
                # This is likely a database user ID
                db_user_id = int(user_id)
            elif platform:
                # We have a platform-specific ID and we know the platform
                with db_session() as db:
                    user = UserRepository.get_by_messenger_id(db, user_id, messenger_type=platform)
                    db_user_id = user.id if user else None
            else:
                # Try to detect platform from ID format
                if user_id.startswith("whatsapp:"):
                    with db_session() as db:
                        user = UserRepository.get_by_messenger_id(db, user_id, messenger_type="whatsapp")
                        db_user_id = user.id if user else None
                elif len(user_id) > 20:  # Viber IDs are typically long UUIDs
                    with db_session() as db:
                        user = UserRepository.get_by_messenger_id(db, user_id, messenger_type="viber")
                        db_user_id = user.id if user else None
                else:
                    # Default to Telegram for shorter IDs
                    with db_session() as db:
                        user = UserRepository.get_by_messenger_id(db, user_id, messenger_type="telegram")
                        db_user_id = user.id if user else None

            if not db_user_id:
                logger.warning(f"No database user found", extra={'user_id': user_id})
                return

            # Fetch images, phones for the ad using the repository
            with db_session() as db:
                ad = db.query(Ad).get(ad_id)
                if not ad:
                    logger.error(f"Ad not found", extra={'ad_id': ad_id})
                    return

                image_urls = [img.image_url for img in ad.images]
                phone_list = [phone.phone for phone in ad.phones if phone.phone]

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
                logger.info(f"Successfully sent ad", extra={
                    'ad_id': ad_id,
                    'user_id': db_user_id
                })
            else:
                logger.error(f"Failed to send ad", extra={
                    'ad_id': ad_id,
                    'user_id': db_user_id
                })

        # Run the async function
        try:
            return asyncio.run(send())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in send_ad_with_extra_buttons", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.send_subscription_notification')
@log_operation("send_subscription_notification")
def send_subscription_notification(user_id, notification_type, data):
    """
    Consolidated task to send subscription-related notifications across platforms.

    Args:
        user_id: Database user ID
        notification_type: Type of notification (payment_success, expiration_reminder, etc.)
        data: Dictionary with notification data
    """
    with log_context(logger, user_id=user_id, notification_type=notification_type):
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
                    logger.error(f"Failed to send notification", extra={
                        'user_id': user_id,
                        'notification_type': notification_type
                    })

                logger.info("Subscription notification sent", extra={
                    'user_id': user_id,
                    'notification_type': notification_type,
                    'success': success
                })
                return success

            except Exception as e:
                logger.error(f"Error in send_subscription_notification", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            asyncio.run(send())
        except RuntimeError as e:
            logger.warning(f"RuntimeError in send_subscription_notification", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(send())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.check_expiring_subscriptions')
@log_operation("check_expiring_subscriptions")
def check_expiring_subscriptions():
    """
    Check for expiring subscriptions and send reminders.
    Replaces duplicate implementations across platform-specific modules.
    """
    with log_context(logger):
        aggregator = LogAggregator(logger, "check_expiring_subscriptions")

        try:
            reminders_sent = 0

            # Check for subscriptions expiring in 3, 2, and 1 days
            for days in [3, 2, 1]:
                # Find users whose subscription expires in exactly `days` days
                with db_session() as db:
                    users = UserRepository.get_users_with_expiring_subscription(db, days)

                for user in users:
                    user_id = user.id
                    end_date = user.subscription_until.strftime("%d.%m.%Y")

                    # Determine the template based on days remaining
                    if days == 1:
                        template = (
                            "⚠️ Ваша підписка закінчується завтра!\n\n"
                            "Дата закінчення: {end_date}\n\n"
                            "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                        )
                    else:
                        # Determine plural form
                        days_word = "день" if days == 1 else "дні" if days < 5 else "днів"
                        template = (
                            "⚠️ Нагадування про підписку\n\n"
                            "Ваша підписка закінчується через {days} "
                            "{days_word}.\n"
                            "Дата закінчення: {end_date}\n\n"
                            "Щоб продовжити користуватися сервісом, оновіть підписку."
                        )

                    # Send notification using the consolidated task
                    send_notification.delay(
                        user_id=user_id,
                        template=template,
                        data={
                            "days": days,
                            "days_word": days_word,
                            "end_date": end_date
                        }
                    )
                    reminders_sent += 1
                    aggregator.add_item({'user_id': user_id, 'days': days}, success=True)

            # Also notify on the day of expiration
            with db_session() as db:
                from datetime import date
                users_today = db.query(User).filter(
                    User.subscription_until.isnot(None),
                    func.date(User.subscription_until) == date.today()
                ).all()

            for user in users_today:
                user_id = user.id
                end_date = user.subscription_until.strftime("%d.%m.%Y %H:%M")

                # Send notification
                send_notification.delay(
                    user_id=user_id,
                    template=(
                        "⚠️ Ваша підписка закінчується сьогодні!\n\n"
                        "Час закінчення: {end_date}\n\n"
                        "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                    ),
                    data={"end_date": end_date}
                )
                reminders_sent += 1
                aggregator.add_item({'user_id': user_id, 'days': 0}, success=True)

            aggregator.log_summary()

            logger.info("Subscription reminders check completed", extra={
                'reminders_sent': reminders_sent
            })
            return {"status": "success", "reminders_sent": reminders_sent}
        except Exception as e:
            logger.error(f"Error checking expiring subscriptions", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return {"status": "error", "error": str(e)}


@celery_app.task(name='common.messaging.tasks.send_batch_notifications')
@log_operation("send_batch_notifications")
def send_batch_notifications(user_ids: List[int], template: str, data: Dict[str, Any] = None,
                             batch_size: int = 50, **kwargs):
    """
    Send notifications to a batch of users.

    Args:
        user_ids: List of database user IDs
        template: Template name or direct text
        data: Data to format the template with
        batch_size: How many users to process in each batch
        **kwargs: Additional options for the messages
    """
    with log_context(logger, total_users=len(user_ids), batch_size=batch_size):
        aggregator = LogAggregator(logger, "send_batch_notifications")

        results = {
            "total": len(user_ids),
            "success": 0,
            "failed": 0
        }

        # Process in batches to avoid overwhelming the system
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i + batch_size]

            for user_id in batch:
                try:
                    send_notification.delay(
                        user_id=user_id,
                        template=template,
                        data=data,
                        **kwargs
                    )
                    results["success"] += 1
                    aggregator.add_item({'user_id': user_id}, success=True)
                except Exception as e:
                    logger.error(f"Error sending notification", exc_info=True, extra={
                        'user_id': user_id,
                        'error_type': type(e).__name__
                    })
                    results["failed"] += 1
                    aggregator.add_error(str(e), {'user_id': user_id})

        aggregator.log_summary()

        logger.info("Batch notifications completed", extra={
            'total': results['total'],
            'success': results['success'],
            'failed': results['failed']
        })
        return results


@celery_app.task(name='common.messaging.tasks.get_description_and_notify')
@log_operation("get_description_and_notify")
def get_description_and_notify(user_id: Union[int, str], resource_url: str, platform: str = None):
    """
    Get the full description of an ad and send it to the user.

    Args:
        user_id: User ID (database ID or platform-specific ID)
        resource_url: URL of the ad to get description for
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, resource_url=resource_url, platform=platform):
        async def process():
            try:
                # Get the full description using repository
                with db_session() as db:
                    # First get the ad by resource URL
                    from common.db.repositories.ad_repository import AdRepository
                    ad = AdRepository.get_by_resource_url(db, resource_url)
                    description = ad.description if ad else None

                if not description:
                    logger.warning(f"No description found", extra={'resource_url': resource_url})
                    from common.messaging.unified_platform_utils import safe_send_message
                    await safe_send_message(
                        user_id=user_id,
                        text="Немає додаткового опису.",
                        platform=platform
                    )
                    return False

                # Send the description
                from common.messaging.unified_platform_utils import safe_send_message
                success = await safe_send_message(
                    user_id=user_id,
                    text=description,
                    platform=platform
                )

                logger.info("Description sent", extra={
                    'user_id': user_id,
                    'resource_url': resource_url,
                    'success': success
                })
                return success
            except Exception as e:
                logger.error(f"Error getting and sending description", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(process())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in get_description_and_notify", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(process())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.process_new_listings')
@log_operation("process_new_listings")
def process_new_listings(ad_ids: List[int], max_notifications_per_user: int = 5):
    """
    Process new listings and send notifications to matching users.

    Args:
        ad_ids: List of new ad IDs
        max_notifications_per_user: Maximum notifications to send to each user
    """
    with log_context(logger, ad_count=len(ad_ids), max_notifications=max_notifications_per_user):
        aggregator = LogAggregator(logger, "process_new_listings")

        try:
            # Find matching users for all ads
            matching_users = {}

            with db_session() as db:
                for ad_id in ad_ids:
                    ad = db.query(Ad).get(ad_id)
                    if ad:
                        # Use the repository to find users for this ad
                        from common.db.repositories.ad_repository import AdRepository
                        matching_users[ad_id] = AdRepository.find_users_for_ad(db, ad)

            # Track notifications sent to each user to avoid spamming
            notifications_sent = {}
            sent_count = 0

            # Process each ad
            for ad_id in ad_ids:
                user_ids = matching_users.get(ad_id, [])

                for user_id in user_ids:
                    # Check if user has reached maximum notifications
                    if notifications_sent.get(user_id, 0) >= max_notifications_per_user:
                        continue

                    # Send notification
                    from common.messaging.consolidated_tasks import send_property_notification
                    send_property_notification.delay(user_id=user_id, ad_id=ad_id)

                    # Increment counter
                    notifications_sent[user_id] = notifications_sent.get(user_id, 0) + 1
                    sent_count += 1
                    aggregator.add_item({'ad_id': ad_id, 'user_id': user_id}, success=True)

            aggregator.log_summary()

            logger.info("New listings processed", extra={
                'ads_processed': len(ad_ids),
                'notifications_sent': sent_count,
                'users_notified': len(notifications_sent)
            })
            return {
                "status": "success",
                "ads_processed": len(ad_ids),
                "notifications_sent": sent_count,
                "users_notified": len(notifications_sent)
            }
        except Exception as e:
            logger.error(f"Error processing new listings", exc_info=True, extra={
                'error_type': type(e).__name__
            })
            return {"status": "error", "error": str(e)}


@celery_app.task(name='common.messaging.tasks.process_show_more_description')
@log_operation("process_show_more_description")
def process_show_more_description(user_id: Union[int, str], resource_url: str, message_id=None, platform=None):
    """
    Consolidated task to handle "show more" functionality across platforms.

    Args:
        user_id: User's platform-specific ID or database user ID
        resource_url: URL of the ad to get description for
        message_id: Optional message ID (for platforms that support editing)
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, resource_url=resource_url, platform=platform):
        async def process():
            try:
                # Get the full description
                full_description = get_full_ad_description(resource_url)
                if not full_description:
                    logger.warning(f"No description found", extra={'resource_url': resource_url})
                    from common.messaging.unified_platform_utils import safe_send_message
                    await safe_send_message(
                        user_id=user_id,
                        text="Немає додаткового опису.",
                        platform=platform
                    )
                    return False

                # Use the platform_utils to resolve user ID and platform info
                from common.messaging.unified_platform_utils import resolve_user_id, get_messenger_instance

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
                            logger.info("Description sent via messaging service", extra={
                                'user_id': db_user_id,
                                'resource_url': resource_url
                            })
                            return True
                    except Exception as e:
                        logger.warning(f"Error using messaging service", exc_info=True, extra={
                            'db_user_id': db_user_id,
                            'error_type': type(e).__name__
                        })

                # If no success with unified service, try platform-specific approach
                if platform_name and platform_id:
                    # For Telegram and if we have a message_id, try to edit the message
                    if platform_name == "telegram" and message_id:
                        try:
                            from common.messaging.unified_platform_utils import safe_edit_message_telegram
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
                            logger.info("Description added via message edit", extra={
                                'platform': platform_name,
                                'message_id': message_id
                            })
                            return True
                        except Exception as e:
                            logger.warning(f"Failed to edit Telegram message", exc_info=True, extra={
                                'error_type': type(e).__name__
                            })

                # If editing failed or not applicable, send as a new message
                from common.messaging.unified_platform_utils import safe_send_message
                success = await safe_send_message(
                    user_id=user_id,
                    text=full_description,
                    platform=platform
                )

                logger.info("Description sent as new message", extra={
                    'user_id': user_id,
                    'platform': platform,
                    'success': success
                })
                return success

            except Exception as e:
                logger.error(f"Error processing show more description", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return False

        # Run the async function
        try:
            return asyncio.run(process())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in process_show_more_description", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(process())
            finally:
                loop.close()


# --- Support-Related Tasks ---

@celery_app.task(name='common.messaging.tasks.start_support_conversation')
@log_operation("start_support_conversation")
def start_support_conversation(user_id, platform=None):
    """
    Start a support conversation with a user.
    Works with any platform (telegram, viber, whatsapp).

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, platform=platform):
        async def execute():
            try:
                # Call the unified handler
                success = await handle_support_command(user_id, platform)
                logger.info("Support conversation started", extra={
                    'user_id': user_id,
                    'platform': platform,
                    'success': success
                })
                return {"success": success}
            except Exception as e:
                logger.error(f"Error starting support conversation", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return {"success": False, "error": str(e)}

        # Run the async function
        try:
            return asyncio.run(execute())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in start_support_conversation", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(execute())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.process_support_category')
@log_operation("process_support_category")
def process_support_category(user_id, category, platform=None):
    """
    Process a selected support category.
    Works with any platform (telegram, viber, whatsapp).

    Args:
        user_id: User's platform-specific ID or database ID
        category: Selected support category
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, category=category, platform=platform):
        async def execute():
            try:
                # Call the unified handler
                success = await handle_support_category(user_id, category, platform)
                logger.info("Support category processed", extra={
                    'user_id': user_id,
                    'category': category,
                    'platform': platform,
                    'success': success
                })
                return {"success": success}
            except Exception as e:
                logger.error(f"Error processing support category", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return {"success": False, "error": str(e)}

        # Run the async function
        try:
            return asyncio.run(execute())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in process_support_category", extra={
                'error_type': type(e).__name__
            })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(execute())
            finally:
                loop.close()


@celery_app.task(name='common.messaging.tasks.forward_to_support')
@log_operation("forward_to_support")
def forward_to_support(user_id, message, category, platform=None):
    """
    Forward a user message to the support system.

    Args:
        user_id: User's platform-specific ID or database ID
        message: User's message to forward
        category: Support category for context
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, category=category, platform=platform):
        async def execute():
            try:
                # Get user information for context
                db_user_id = None
                if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
                    db_user_id = int(user_id)
                elif platform:
                    db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type=platform)

                if not db_user_id:
                    logger.warning(f"Could not resolve database user ID", extra={'user_id': user_id})

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
                logger.info(f"Support request received", extra=support_data)

                # Generate ticket ID
                ticket_id = str(uuid.uuid4())

                logger.info("Support request forwarded", extra={
                    'user_id': user_id,
                    'ticket_id': ticket_id,
                    'category': category
                })
                # Return success
                return {"success": True, "support_ticket_id": ticket_id}
            except Exception as e:
                logger.error(f"Error forwarding to support", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return {"success": False, "error": str(e)}

        # Run the async function
        try:
            return asyncio.run(execute())
        except RuntimeError as e:
            # Handle case where there's already an event loop
            logger.warning(f"RuntimeError in forward_to_support", extra={
                'error_type': type(e).__name__
            })
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