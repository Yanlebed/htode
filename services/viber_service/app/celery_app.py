# app/celery_app.py

from common.celery_app import celery_app

# Import tasks after initializing celery_app to avoid circular imports
from . import tasks

# Make sure to export the celery_app for worker to find it
__all__ = ['celery_app']