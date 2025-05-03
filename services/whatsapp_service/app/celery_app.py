# services/whatsapp_service/app/celery_app.py

from common.celery_app import celery_app
from common.utils.logging_config import log_context

# Import the service logger
from . import logger

# Import tasks after initializing celery_app to avoid circular imports
from . import tasks

# WhatsApp-specific configuration
logger.info("Configuring Celery for WhatsApp service", extra={
    'broker_url': celery_app.conf.broker_url,
    'worker_concurrency': celery_app.conf.worker_concurrency,
})

celery_app.conf.update(
    # For example, WhatsApp might need a longer task timeout due to API rate limits
    task_time_limit=300,  # 5 minutes timeout
    task_soft_time_limit=240,  # 4 minutes soft timeout
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks to prevent memory leaks
)

logger.info("Celery configuration updated for WhatsApp service", extra={
    'task_time_limit': celery_app.conf.task_time_limit,
    'task_soft_time_limit': celery_app.conf.task_soft_time_limit,
    'worker_max_tasks_per_child': celery_app.conf.worker_max_tasks_per_child,
})

# Note: The beat schedule is already defined in common/celery_app.py
# and the rate limiting for WhatsApp tasks is already set there as well

# Make sure to export the celery_app for worker to find it
__all__ = ['celery_app']