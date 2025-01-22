# services/telegram_service/Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Копируем общие модули
COPY common /app/common

# Копируем код конкретного сервиса
COPY services/telegram_service/app /app/app

# Устанавливаем зависимости
COPY services/telegram_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем PYTHONPATH
ENV PYTHONPATH=/app/common

# Запуск бота
CMD ["python", "-m", "app.main"]
