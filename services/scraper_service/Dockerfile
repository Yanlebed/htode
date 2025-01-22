# services/scraper_service/Dockerfile

FROM python:3.10-slim

WORKDIR /app

COPY common /app/common
COPY services/scraper_service/app /app/app

COPY services/scraper_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app

CMD ["celery", "-A", "app.celery_app.celery_app", "worker", "--loglevel=info", "-Q", "scrape_queue"]
