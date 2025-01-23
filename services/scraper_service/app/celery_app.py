# services/scraper_service/app/celery_app.py

from celery import Celery
import os
from celery.schedules import schedule  # or crontab, if you prefer

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("scraper_service", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_routes={
        'scraper_service.app.tasks.*': {'queue': 'scrape_queue'},
    },
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    # 'timezone': 'UTC',  # uncomment/adjust as needed
    # 'enable_utc': True,
)

# ===========================
# BEAT CONFIGURATION SECTION
# ===========================
# We'll read the interval from an environment variable or default to 5 minutes (300 seconds).
SCRAPER_INTERVAL_MINUTES = int(os.getenv("SCRAPER_INTERVAL", 1))
SCRAPER_INTERVAL_SECONDS = SCRAPER_INTERVAL_MINUTES * 60

celery_app.conf.beat_schedule = {
    'fetch-new-ads-every-N-minutes': {
        'task': 'scraper_service.app.tasks.fetch_new_ads',
        'schedule': SCRAPER_INTERVAL_SECONDS,
        # 'args': (...) if needed
    },
}

# 2) Autodiscover tasks from the specified module
celery_app.autodiscover_tasks(['scraper_service.app'], force=True)