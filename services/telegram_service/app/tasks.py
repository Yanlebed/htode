# services/telegram_service/app/tasks.py
from common.celery_app import celery_app
from aiogram.types import CallbackQuery

# Import service logger and logging utilities
from . import logger
from common.utils.logging_config import log_operation, log_context

# Import the bot for the callback handler
from .bot import dp


# Create the tasks directly without using the task registry
# This avoids the circular import issue
@celery_app.task(name='telegram_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(telegram_id: int, text: str, s3_image_links: str, resource_url: str, ad_id: int,
                               ad_external_id: str):
    """Send ad with extra buttons to Telegram user"""
    # Import messaging_service here to avoid circular import
    from common.messaging.service import messaging_service

    return messaging_service.send_ad_with_extra_buttons(
        user_id=telegram_id,
        platform="telegram",
        text=text,
        image_url=s3_image_links,
        resource_url=resource_url,
        ad_id=ad_id,
        external_id=ad_external_id
    )


@celery_app.task(name='telegram_service.app.tasks.send_subscription_notification')
def send_subscription_notification(telegram_id: int, notification_type: str, data: dict):
    """Send subscription notification to Telegram user"""
    # Import messaging_service here to avoid circular import
    from common.messaging.service import messaging_service

    return messaging_service.send_subscription_notification(
        user_id=telegram_id,
        platform="telegram",
        notification_type=notification_type,
        data=data
    )


# Add the missing tasks that Celery is looking for
@celery_app.task(name='telegram_service.app.tasks.send_subscription_reminders')
def send_subscription_reminders():
    """Send subscription reminders to users"""
    with log_context(logger, task_name="send_subscription_reminders"):
        logger.info("Starting subscription reminders task")

        # Import here to avoid circular dependencies
        from common.db.operations import get_users_for_reminders
        from common.messaging.service import messaging_service

        try:
            # Get users who need reminders
            users = get_users_for_reminders()
            logger.info(f"Found {len(users)} users for reminders")

            for user in users:
                telegram_id = user.get('telegram_id')
                if telegram_id:
                    reminder_text = "Ваша підписка закінчується незабаром. Не забудьте поновити!"

                    messaging_service.send_subscription_notification(
                        user_id=telegram_id,
                        platform="telegram",
                        notification_type="subscription_reminder",
                        data={"text": reminder_text}
                    )

            return {"status": "success", "users_notified": len(users)}

        except Exception as e:
            logger.error("Error in send_subscription_reminders", exc_info=True)
            return {"status": "error", "error": str(e)}


@celery_app.task(name='telegram_service.app.tasks.check_expiring_subscriptions')
def check_expiring_subscriptions():
    """Check for expiring subscriptions and notify users"""
    with log_context(logger, task_name="check_expiring_subscriptions"):
        logger.info("Starting check for expiring subscriptions")

        # Import here to avoid circular dependencies
        from common.db.operations import get_expiring_subscriptions
        from common.messaging.service import messaging_service

        try:
            # Get subscriptions expiring soon
            expiring_subscriptions = get_expiring_subscriptions()
            logger.info(f"Found {len(expiring_subscriptions)} expiring subscriptions")

            for subscription in expiring_subscriptions:
                user_id = subscription.get('user_id')
                telegram_id = subscription.get('telegram_id')

                if telegram_id:
                    days_left = subscription.get('days_left', 0)

                    if days_left <= 1:
                        notification_text = "Ваша підписка закінчується сьогодні! Поновіть зараз, щоб не втратити доступ."
                    elif days_left <= 3:
                        notification_text = f"Ваша підписка закінчується через {days_left} дні. Рекомендуємо поновити."
                    elif days_left <= 7:
                        notification_text = f"Ваша підписка закінчується через {days_left} днів."
                    else:
                        continue  # Don't notify for subscriptions expiring in more than 7 days

                    messaging_service.send_subscription_notification(
                        user_id=telegram_id,
                        platform="telegram",
                        notification_type="subscription_expiring",
                        data={"text": notification_text}
                    )

            return {"status": "success", "subscriptions_checked": len(expiring_subscriptions)}

        except Exception as e:
            logger.error("Error in check_expiring_subscriptions", exc_info=True)
            return {"status": "error", "error": str(e)}


# This handler needs to remain in the Telegram service as it's tied to the callback query handler
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("show_more:"))
@log_operation("show_more_description")
async def handle_show_more(callback_query: CallbackQuery):
    """
    Handle the show_more callback query and delegate to the unified task.
    This remains in the Telegram service as it's tied to the callback query handler.
    """
    with log_context(logger, user_id=callback_query.from_user.id, callback_data=callback_query.data):
        # Extract the resource_url from the callback data
        try:
            _, resource_url = callback_query.data.split("show_more:")
        except Exception as e:
            logger.warning("Invalid callback data format", extra={"error": str(e)})
            await callback_query.answer("Невірні дані.", show_alert=True)
            return

        # Acknowledge the callback query immediately
        await callback_query.answer("Отримання повного опису...")

        # Import here to avoid circular dependency
        from common.messaging.tasks import process_show_more_description

        # Call the unified task to handle the show more functionality
        # Pass both the user_id and message_id so it can edit the message if possible
        process_show_more_description.delay(
            user_id=callback_query.from_user.id,
            resource_url=resource_url,
            message_id=callback_query.message.message_id,
            platform="telegram"
        )