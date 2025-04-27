# services/whatsapp_service/app/tasks.py
import logging
from common.celery_app import celery_app
from common.messaging.task_registry import register_platform_tasks
from common.db.session import db_session
from common.db.repositories.media_repository import MediaRepository
from .bot import client, TWILIO_PHONE_NUMBER

logger = logging.getLogger(__name__)

# Register standard messaging tasks for WhatsApp
registered_tasks = register_platform_tasks(
    platform_name="whatsapp",
    task_module_path="whatsapp_service.app.tasks"
)

# Export the registered tasks for direct use
send_ad_with_extra_buttons = registered_tasks['send_ad_with_extra_buttons']
send_subscription_notification = registered_tasks['send_subscription_notification']


# Keep WhatsApp-specific tasks that have no common equivalent
@celery_app.task(name='whatsapp_service.app.tasks.check_template_status')
def check_template_status():
    """
    Check the status of WhatsApp message templates.
    """
    from common.db.session import db_session
    from common.db.repositories.user_repository import UserRepository

    logger.info("Checking WhatsApp template status")

    try:
        # Use Twilio client to check template status
        templates = client.messaging.services(TWILIO_PHONE_NUMBER.split(":")[1]).message_templates.list()

        for template in templates:
            logger.info(f"Template {template.sid}: Status={template.status}")

            # Log rejected templates for review
            if template.status == 'rejected':
                logger.warning(f"Template {template.sid} rejected: {template.reason}")

                # Notify admins about rejected templates
                with db_session() as db:
                    # Use repository method instead of raw SQL
                    admin = UserRepository.get_admin_user(db)

                if admin:
                    admin_id = admin.id
                    notification_text = (
                        f"⚠️ WhatsApp template {template.sid} was rejected\n"
                        f"Reason: {template.reason}\n\n"
                        "Please review and update the template."
                    )

                    # Use the unified task to send the notification
                    send_subscription_notification.delay(
                        user_id=admin_id,
                        notification_type="template_rejected",
                        data={"text": notification_text}
                    )

        return {"status": "success", "templates_checked": len(templates)}

    except Exception as e:
        logger.error(f"Error checking WhatsApp template status: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task(name='whatsapp_service.app.tasks.process_media_messages')
def process_media_messages():
    """
    Process and store media messages sent by users.
    """
    from common.utils.s3_utils import _upload_image_to_s3

    logger.info("Processing WhatsApp media messages")

    try:
        with db_session() as db:
            # Use repository method instead of raw SQL
            unprocessed_media = MediaRepository.get_unprocessed_media(db)

            for message in unprocessed_media:
                message_id = message.id
                media_url = message.media_url

                logger.info(f"Processing media message {message_id} with URL {media_url}")

                try:
                    # Generate a unique ID for the media
                    unique_id = f"whatsapp_media_{message_id}"

                    # Upload to S3
                    s3_url = _upload_image_to_s3(media_url, unique_id, max_retries=3)

                    if s3_url:
                        # Update the record with the permanent URL using repository
                        MediaRepository.update_media_status(db, message_id, s3_url, True)
                        logger.info(f"Successfully processed media message {message_id}")
                    else:
                        logger.warning(f"Failed to upload media for message {message_id}")

                except Exception as media_err:
                    logger.error(f"Error processing media message {message_id}: {media_err}")

            return {"status": "success", "messages_processed": len(unprocessed_media)}

    except Exception as e:
        logger.error(f"Error in process_media_messages: {e}")
        return {"status": "error", "error": str(e)}