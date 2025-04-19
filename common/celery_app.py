# common/celery_app.py
from celery import Celery
from celery.schedules import crontab
from common.config import REDIS_URL

celery_app = Celery("shared_app", broker=REDIS_URL, backend=REDIS_URL)

# Common configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],

    # Timezone and time settings
    timezone='UTC',
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,  # Tasks are acknowledged after execution (not before)
    task_reject_on_worker_lost=True,  # Reject tasks if worker crashes or disconnects
    worker_prefetch_multiplier=1,  # Prefetch just one task at a time for better load balancing

    # Retry settings
    task_default_retry_delay=60,  # 1 minute delay between retries
    task_max_retries=3,  # Maximum number of retries

    # Result backend settings
    result_expires=86400,  # Results expire after 1 day

    # Error handling
    task_ignore_result=False,  # Store task results by default
    task_store_errors_even_if_ignored=True,  # Store errors even if results are ignored

    # Queue timeout settings
    broker_transport_options={
        'visibility_timeout': 43200,  # 12 hours (in seconds)
    },

    # Rate limiting - tasks per worker per time unit
    task_annotations={
        'scraper_service.app.tasks.fetch_new_ads': {'rate_limit': '1/m'},  # 1 per minute
        'notifier_service.app.tasks.notify_user_with_ads': {'rate_limit': '10/m'},  # 10 per minute
    },
)

# Service-specific queue routing
celery_app.conf.update(
    task_routes={
        'notifier_service.app.tasks.*': {'queue': 'notify_queue'},
        'telegram_service.app.tasks.*': {'queue': 'telegram_queue'},
        'scraper_service.app.tasks.*': {'queue': 'scrape_queue'},
    },
)

# Scheduled tasks
celery_app.conf.beat_schedule = {
    'subscription-reminders-daily': {
        'task': 'telegram_service.app.tasks.send_subscription_reminders',
        'schedule': crontab(hour=10, minute=0),  # Run daily at 10:00 AM
    },
    'fetch-new-ads-every-5-minutes': {
        'task': 'scraper_service.app.tasks.fetch_new_ads',
        'schedule': 300.0,  # 5 minutes in seconds
    },
    'system-maintenance-weekly': {
        'task': 'system.maintenance.cleanup_old_ads',
        'schedule': crontab(day_of_week='sun', hour=2, minute=0),  # Sunday at 2 AM
        'kwargs': {'days_old': 30},  # Clean ads older than 30 days
    },
    'check-expiring-subscriptions-daily': {
        'task': 'telegram_service.app.tasks.check_expiring_subscriptions',
        'schedule': crontab(hour=9, minute=0),  # Run daily at 9:00 AM
    },
}
