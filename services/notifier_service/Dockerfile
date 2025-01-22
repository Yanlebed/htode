# services/notifier_service/Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Копируем общие модули
COPY common /app/common

# Копируем код конкретного сервиса
COPY services/notifier_service/app /app/app

# Устанавливаем зависимости
COPY services/notifier_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем PYTHONPATH
ENV PYTHONPATH=/app/common

# Запуск Celery worker
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--queues=notify_queue"]
