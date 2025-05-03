# services/viber_service/app/tasks.py

from common.celery_app import celery_app
from common.messaging.task_registry import register_platform_tasks

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation, LogAggregator

# Import the service logger
from .. import logger

logger.info("Initializing Viber service tasks")

# Register standard messaging tasks for Viber
registered_tasks = register_platform_tasks(
    platform_name="viber",
    task_module_path="viber_service.app.tasks"
)

# Export the registered tasks for direct use
send_ad_with_extra_buttons = registered_tasks['send_ad_with_extra_buttons']
send_subscription_notification = registered_tasks['send_subscription_notification']

logger.info("Standard messaging tasks registered for Viber", extra={
    'registered_tasks': list(registered_tasks.keys())
})


# Keep Viber-specific task that has no common equivalent
@celery_app.task(name='viber_service.app.tasks.check_expired_conversations')
@log_operation("check_expired_conversations")
def check_expired_conversations():
    """
    Check for expired Viber conversations and clean up.
    """
    from common.db.session import db_session
    from common.db.repositories.user_repository import UserRepository

    logger.info("Starting check for expired Viber conversations")
    aggregator = LogAggregator(logger, "check_expired_conversations")

    try:
        with db_session() as db:
            # Use repository method instead of raw SQL
            users_with_expired_conversations = UserRepository.get_users_with_expired_viber_conversations(db)

            logger.info(f"Found users with expired conversations", extra={
                'user_count': len(users_with_expired_conversations)
            })

            for user in users_with_expired_conversations:
                user_id = user.id
                viber_id = user.viber_id

                with log_context(logger, user_id=user_id, viber_id=viber_id):
                    try:
                        logger.info(f"Processing expired conversation", extra={
                            'user_id': user_id,
                            'viber_id': viber_id
                        })

                        # Update the user using repository
                        success = UserRepository.mark_viber_conversation_expired(db, user_id)

                        if success:
                            aggregator.add_item({
                                'user_id': user_id,
                                'viber_id': viber_id,
                                'status': 'marked_expired'
                            }, success=True)

                            logger.info(f"Marked conversation as expired", extra={
                                'user_id': user_id,
                                'viber_id': viber_id
                            })
                        else:
                            aggregator.add_error(
                                f"Failed to mark conversation as expired for user {user_id}",
                                {'user_id': user_id, 'viber_id': viber_id}
                            )

                        # Send a reminder message via another channel if available
                        try:
                            # Check if user has other messaging channels
                            if user.telegram_id or user.whatsapp_id:
                                reminder_text = (
                                    "Ваша Viber сесія закінчилася. Щоб продовжити отримувати сповіщення через Viber, "
                                    "будь ласка, напишіть будь-яке повідомлення нашому боту."
                                )

                                logger.info(f"Sending reminder via alternative channel", extra={
                                    'user_id': user_id,
                                    'has_telegram': bool(user.telegram_id),
                                    'has_whatsapp': bool(user.whatsapp_id)
                                })

                                # Use the unified task to send the notification
                                send_subscription_notification.delay(
                                    user_id=user_id,
                                    notification_type="conversation_expired",
                                    data={"text": reminder_text}
                                )
                            else:
                                logger.info(f"No alternative channels available for reminder", extra={
                                    'user_id': user_id
                                })

                        except Exception as channel_err:
                            logger.error(f"Error sending channel reminder", exc_info=True, extra={
                                'user_id': user_id,
                                'error_type': type(channel_err).__name__
                            })
                            aggregator.add_error(
                                f"Failed to send reminder: {str(channel_err)}",
                                {'user_id': user_id}
                            )

                    except Exception as user_err:
                        logger.error(f"Error processing user", exc_info=True, extra={
                            'user_id': user_id,
                            'viber_id': viber_id,
                            'error_type': type(user_err).__name__
                        })
                        aggregator.add_error(
                            f"Error processing user {user_id}: {str(user_err)}",
                            {'user_id': user_id, 'viber_id': viber_id}
                        )

            # Log aggregated summary
            aggregator.log_summary()

            return {
                "status": "success",
                "users_processed": len(users_with_expired_conversations),
                "successful": len([item for item in aggregator.items if item['success']]),
                "errors": len(aggregator.errors)
            }

    except Exception as e:
        logger.error(f"Error checking expired Viber conversations", exc_info=True, extra={
            'error_type': type(e).__name__
        })
        return {"status": "error", "error": str(e)}