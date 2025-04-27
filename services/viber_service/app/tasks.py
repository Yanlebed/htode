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
    """
    from common.db.session import db_session
    from common.db.repositories.user_repository import UserRepository

    logger.info("Checking for expired Viber conversations")

    try:
        with db_session() as db:
            # Use repository method instead of raw SQL
            users_with_expired_conversations = UserRepository.get_users_with_expired_viber_conversations(db)

            for user in users_with_expired_conversations:
                user_id = user.id
                viber_id = user.viber_id

                logger.info(f"Marking Viber conversation as expired for user {user_id} (Viber ID: {viber_id})")

                # Update the user using repository
                UserRepository.mark_viber_conversation_expired(db, user_id)

                # Send a reminder message via another channel if available
                try:
                    # Check if user has other messaging channels
                    if user.telegram_id or user.whatsapp_id:
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

            return {"status": "success", "users_processed": len(users_with_expired_conversations)}

    except Exception as e:
        logger.error(f"Error checking expired Viber conversations: {e}")
        return {"status": "error", "error": str(e)}