# services/viber_service/app/tasks.py

import logging
from common.celery_app import celery_app
from common.messaging.task_registry import register_platform_tasks

logger = logging.getLogger(__name__)

# Register standard messaging tasks for Viber
registered_tasks = register_platform_tasks(
    platform_name="viber",
    task_module_path="viber_service.app.tasks"
)

# Export the registered tasks for direct use
send_ad_with_extra_buttons = registered_tasks['send_ad_with_extra_buttons']
send_subscription_notification = registered_tasks['send_subscription_notification']


# Keep Viber-specific task that has no common equivalent
@celery_app.task(name='viber_service.app.tasks.check_expired_conversations')
def check_expired_conversations():
    """
    Check for expired Viber conversations and clean up.
    This is Viber-specific and doesn't have an equivalent in other platforms.

    Viber conversations expire after 24 hours, so we need to handle this.
    """
    from common.db.database import execute_query

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

            # Send a reminder message via another channel if available
            try:
                # Check if user has other messaging channels
                check_sql = """
                            SELECT telegram_id, whatsapp_id
                            FROM users
                            WHERE id = %s
                              AND (telegram_id IS NOT NULL OR whatsapp_id IS NOT NULL)
                            """
                other_channels = execute_query(check_sql, [user_id], fetchone=True)

                if other_channels:
                    reminder_text = (
                        "Ваша Viber сесія закінчилася. Щоб продовжити отримувати сповіщення через Viber, "
                        "будь ласка, напишіть будь-яке повідомлення нашому боту."
                    )

                    # Use the unified task to send the notification
                    send_subscription_notification.delay(
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