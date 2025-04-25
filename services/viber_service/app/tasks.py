# services/viber_service/app/tasks.py

import logging
from datetime import datetime

from common.celery_app import celery_app
from common.db.database import execute_query
from common.messaging.tasks import (
    send_ad_with_extra_buttons as unified_send_ad,
    send_subscription_notification as unified_send_notification
)
from .bot import viber

logger = logging.getLogger(__name__)


# Redirect to unified implementation
@celery_app.task(name='viber_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id, text, s3_image_url, resource_url, ad_id, ad_external_id):
    """
    Redirects to the unified send_ad_with_extra_buttons task.
    Specifies 'viber' as the platform for proper handling.
    Kept for backward compatibility.
    """
    return unified_send_ad.delay(
        user_id=user_id,
        text=text,
        s3_image_url=s3_image_url,
        resource_url=resource_url,
        ad_id=ad_id,
        ad_external_id=ad_external_id,
        platform="viber"
    )


# Redirect to unified implementation
@celery_app.task(name='viber_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id, notification_type, data):
    """
    Redirects to the unified send_subscription_notification task.
    Kept for backward compatibility.
    """
    return unified_send_notification.delay(user_id, notification_type, data)


@celery_app.task(name='viber_service.app.tasks.check_expired_conversations')
def check_expired_conversations():
    """
    Check for expired Viber conversations and clean up.
    This is Viber-specific and doesn't have an equivalent in other platforms,
    so it remains a standalone task.

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

                    # Use unified task to send the notification
                    unified_send_notification.delay(
                        user_id=user_id,
                        notification_type="conversation_expired",
                        data={"text": reminder_text}
                    )
            except Exception as channel_err:
                logger.error(f"Error sending channel reminder: {channel_err}")

        return {"status": "success", "users_processed": len(users)}

    except Exception as e:
        logger.error(f"Error checking expired Viber conversations: {e}")
        return {"status": "error", "error": str(e)}