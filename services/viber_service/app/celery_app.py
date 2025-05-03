# services/viber_service/app/celery_app.py

from common.celery_app import celery_app

# Import logging utilities
from common.utils.logging_config import log_context

# Import the service logger
from .. import logger

# Import tasks after initializing celery_app to avoid circular imports
from . import tasks

# Make sure to export the celery_app for worker to find it
__all__ = ['celery_app']

logger.info("Viber service Celery app initialized", extra={
    'app_name': celery_app.main,
    'broker': celery_app.conf.broker_url
})