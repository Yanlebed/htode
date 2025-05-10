# services/whatsapp_service/app/tasks.py
from common.celery_app import celery_app
from common.utils.logging_config import log_context, log_operation, LogAggregator
from .bot import client, TWILIO_PHONE_NUMBER

# Import the service logger
from . import logger


# Create the tasks directly without using the task registry
# This avoids the circular import issue
@celery_app.task(name='whatsapp_service.app.tasks.send_ad_with_extra_buttons')
def send_ad_with_extra_buttons(user_id: str, text: str, image_url: str, resource_url: str, ad_id: int,
                               external_id: str):
    """Send ad with extra buttons to WhatsApp user"""
    # Import messaging_service here to avoid circular import
    from common.messaging.service import messaging_service

    return messaging_service.send_ad_with_extra_buttons(
        user_id=user_id,
        platform="whatsapp",
        text=text,
        image_url=image_url,
        resource_url=resource_url,
        ad_id=ad_id,
        external_id=external_id
    )


@celery_app.task(name='whatsapp_service.app.tasks.send_subscription_notification')
def send_subscription_notification(user_id: str, notification_type: str, data: dict):
    """Send subscription notification to WhatsApp user"""
    # Import messaging_service here to avoid circular import
    from common.messaging.service import messaging_service

    return messaging_service.send_subscription_notification(
        user_id=user_id,
        platform="whatsapp",
        notification_type=notification_type,
        data=data
    )


# Keep WhatsApp-specific tasks that have no common equivalent
@celery_app.task(name='whatsapp_service.app.tasks.check_template_status')
@log_operation("check_template_status")
def check_template_status():
    """
    Check the status of WhatsApp message templates.
    """
    from common.db.session import db_session
    from common.db.repositories.user_repository import UserRepository

    logger.info("Checking WhatsApp template status")
    aggregator = LogAggregator(logger, "check_template_status")

    try:
        # Use Twilio client to check template status
        templates = client.messaging.services(TWILIO_PHONE_NUMBER.split(":")[1]).message_templates.list()

        for template in templates:
            with log_context(logger, template_sid=template.sid, template_status=template.status):
                logger.info(f"Template {template.sid}: Status={template.status}")

                # Log rejected templates for review
                if template.status == 'rejected':
                    logger.warning(f"Template {template.sid} rejected: {template.reason}")
                    aggregator.add_error(f"Template rejected: {template.reason}", {'template_sid': template.sid})

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

                        # Use the task to send the notification
                        send_subscription_notification.delay(
                            user_id=admin_id,
                            notification_type="template_rejected",
                            data={"text": notification_text}
                        )
                else:
                    aggregator.add_item({'template_sid': template.sid, 'status': template.status}, success=True)

        aggregator.log_summary()
        return {"status": "success", "templates_checked": len(templates)}

    except Exception as e:
        logger.error(f"Error checking WhatsApp template status", exc_info=True, extra={
            'error_type': type(e).__name__
        })
        return {"status": "error", "error": str(e)}


@celery_app.task(name='whatsapp_service.app.tasks.process_media_messages')
@log_operation("process_media_messages")
def process_media_messages():
    """
    Process and store media messages sent by users.
    """
    from common.utils.s3_utils import _upload_image_to_s3
    from common.db.session import db_session
    from common.db.repositories.media_repository import MediaRepository

    logger.info("Processing WhatsApp media messages")
    aggregator = LogAggregator(logger, "process_media_messages")

    try:
        with db_session() as db:
            # Use repository method instead of raw SQL
            unprocessed_media = MediaRepository.get_unprocessed_media(db)

            for message in unprocessed_media:
                message_id = message.id
                media_url = message.media_url

                with log_context(logger, message_id=message_id, media_url=media_url):
                    logger.info(f"Processing media message {message_id}")

                    try:
                        # Generate a unique ID for the media
                        unique_id = f"whatsapp_media_{message_id}"

                        # Upload to S3
                        s3_url = _upload_image_to_s3(media_url, unique_id, max_retries=3)

                        if s3_url:
                            # Update the record with the permanent URL using repository
                            MediaRepository.update_media_status(db, message_id, s3_url, True)
                            logger.info(f"Successfully processed media message {message_id}")
                            aggregator.add_item({'message_id': message_id, 's3_url': s3_url}, success=True)
                        else:
                            logger.warning(f"Failed to upload media for message {message_id}")
                            aggregator.add_error("Failed to upload to S3", {'message_id': message_id})

                    except Exception as media_err:
                        logger.error(f"Error processing media message", exc_info=True, extra={
                            'message_id': message_id,
                            'error_type': type(media_err).__name__
                        })
                        aggregator.add_error(str(media_err), {'message_id': message_id})

            aggregator.log_summary()
            return {"status": "success", "messages_processed": len(unprocessed_media)}

    except Exception as e:
        logger.error(f"Error in process_media_messages", exc_info=True, extra={
            'error_type': type(e).__name__
        })
        return {"status": "error", "error": str(e)}