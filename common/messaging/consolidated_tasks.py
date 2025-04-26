# common/messaging/consolidated_tasks.py

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

from common.celery_app import celery_app
from common.db.database import execute_query
from common.db.models import (
    get_full_ad_data, get_ad_images, get_full_ad_description,
    get_platform_ids_for_user, get_db_user_id_by_telegram_id
)
from common.messaging.unified_platform_utils import safe_send_message
from common.messaging.service import messaging_service

logger = logging.getLogger(__name__)


@celery_app.task(name='common.messaging.consolidated_tasks.send_notification')
def send_notification(user_id: Union[int, str], template: str, data: Dict[str, Any] = None,
                      platform: str = None, **kwargs):
    """
    Send a notification using a template.

    Args:
        user_id: User ID (database ID or platform-specific ID)
        template: Template name or direct text
        data: Data to format the template with
        platform: Optional platform override
        **kwargs: Additional options for the message
    """

    async def send():
        try:
            # Format template if data is provided
            text = template
            if data:
                try:
                    # Try to interpolate using format() method
                    text = template.format(**data)
                except (KeyError, ValueError):
                    # Fall back to direct template
                    logger.warning(f"Unable to format template: {template} with data: {data}")

            # Send the notification
            success = await safe_send_message(
                user_id=user_id,
                text=text,
                platform=platform,
                **kwargs
            )

            return success
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
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


@celery_app.task(name='common.messaging.consolidated_tasks.send_property_notification')
def send_property_notification(user_id: Union[int, str], ad_id: int, platform: str = None):
    """
    Send a property notification with all necessary data and buttons.

    Args:
        user_id: User ID (database ID or platform-specific ID)
        ad_id: Database ID of the ad
        platform: Optional platform override
    """

    async def send():
        try:
            # Get complete ad data
            ad_data = get_full_ad_data(ad_id)
            if not ad_data:
                logger.error(f"Ad data not found for ad_id: {ad_id}")
                return False

            # Get the primary image
            images = get_ad_images(ad_id)
            primary_image = images[0] if images else None

            # Send via the unified messaging service
            if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()):
                # This is a database user ID, we can use the messaging service directly
                db_user_id = int(user_id)
                success = await messaging_service.send_ad(
                    user_id=db_user_id,
                    ad_data=ad_data,
                    image_url=primary_image
                )
            else:
                # This is a platform-specific ID
                platform_name = platform or "telegram"  # Default to telegram if not specified

                # Get the messenger for this platform
                messenger = messaging_service.get_messenger(platform_name)
                if not messenger:
                    logger.error(f"No messenger available for platform {platform_name}")
                    return False

                # Format the user ID
                formatted_id = await messenger.format_user_id(user_id)

                # Send the ad
                await messenger.send_ad(
                    user_id=formatted_id,
                    ad_data=ad_data,
                    image_url=primary_image
                )
                success = True

            return success
        except Exception as e:
            logger.error(f"Error sending property notification: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_property_notification: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.consolidated_tasks.send_subscription_reminder')
def send_subscription_reminder():
    """
    Check for expiring subscriptions and send reminders.
    Replaces platform-specific implementations.
    """
    try:
        reminders_sent = 0

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

                # Determine the template based on days remaining
                if days == 1:
                    template = (
                        "⚠️ Ваша підписка закінчується завтра!\n\n"
                        "Дата закінчення: {end_date}\n\n"
                        "Щоб не втратити доступ до сервісу, оновіть підписку зараз."
                    )
                else:
                    template = (
                        "⚠️ Нагадування про підписку\n\n"
                        "Ваша підписка закінчується через {days} "
                        "{days_word}.\n"
                        "Дата закінчення: {end_date}\n\n"
                        "Щоб продовжити користуватися сервісом, оновіть підписку."
                    )

                # Determine plural form
                days_word = "день" if days == 1 else "дні" if days < 5 else "днів"

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

        return {"status": "success", "reminders_sent": reminders_sent}
    except Exception as e:
        logger.error(f"Error sending subscription reminders: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task(name='common.messaging.consolidated_tasks.send_batch_notifications')
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
            except Exception as e:
                logger.error(f"Error sending notification to user {user_id}: {e}")
                results["failed"] += 1

    return results


@celery_app.task(name='common.messaging.consolidated_tasks.get_description_and_notify')
def get_description_and_notify(user_id: Union[int, str], resource_url: str, platform: str = None):
    """
    Get the full description of an ad and send it to the user.

    Args:
        user_id: User ID (database ID or platform-specific ID)
        resource_url: URL of the ad to get description for
        platform: Optional platform override
    """

    async def process():
        try:
            # Get the full description
            description = get_full_ad_description(resource_url)
            if not description:
                logger.warning(f"No description found for resource {resource_url}")
                await safe_send_message(
                    user_id=user_id,
                    text="Немає додаткового опису.",
                    platform=platform
                )
                return False

            # Send the description
            success = await safe_send_message(
                user_id=user_id,
                text=description,
                platform=platform
            )

            return success
        except Exception as e:
            logger.error(f"Error getting and sending description: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(process())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in get_description_and_notify: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(process())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.consolidated_tasks.process_new_listings')
def process_new_listings(ad_ids: List[int], max_notifications_per_user: int = 5):
    """
    Process new listings and send notifications to matching users.

    Args:
        ad_ids: List of new ad IDs
        max_notifications_per_user: Maximum notifications to send to each user
    """
    from common.db.models import batch_find_users_for_ads

    try:
        # Find matching users for all ads
        matching_users = batch_find_users_for_ads(ad_ids)

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
                send_property_notification.delay(user_id=user_id, ad_id=ad_id)

                # Increment counter
                notifications_sent[user_id] = notifications_sent.get(user_id, 0) + 1
                sent_count += 1

        return {
            "status": "success",
            "ads_processed": len(ad_ids),
            "notifications_sent": sent_count,
            "users_notified": len(notifications_sent)
        }
    except Exception as e:
        logger.error(f"Error processing new listings: {e}")
        return {"status": "error", "error": str(e)}