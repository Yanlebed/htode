# services/scraper_service/Dockerfile

FROM python:3.10-slim

# 1) Install system dependencies needed by Chromium/Playwright
#    (list may vary depending on your environment):
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgtk-3-0 \
    libasound2 \
    wget \
    ca-certificates \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY common /app/common
COPY services/scraper_service /app/scraper_service


COPY requirements/scraper.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

#    A) pip install playwright (whatever version you like)
#    B) Then run "playwright install --with-deps chromium"
RUN pip install --no-cache-dir playwright==1.36.0
RUN playwright install --with-deps chromium

ENV PYTHONPATH=/app

CMD ["celery", "-A", "app.celery_app.celery_app", "worker", "--loglevel=info", "-Q", "scrape_queue"]
