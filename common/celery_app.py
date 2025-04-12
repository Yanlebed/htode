# common/celery_app.py

from celery import Celery
import os

# Чтение переменной окружения для REDIS_URL
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery("shared_app", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_routes={
        'notifier_service.app.tasks.*': {'queue': 'notify_queue'},
        'telegram_service.app.tasks.*': {'queue': 'telegram_queue'},
    },
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
)

# celery_app.conf.beat_schedule = {
#     'subscription-reminders-daily': {
#         'task': 'telegram_service.app.tasks.send_subscription_reminders',
#         'schedule': crontab(hour=10, minute=0),
#     },
# }
# # TODO: check for crontab