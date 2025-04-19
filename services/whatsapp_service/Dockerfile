# services/whatsapp_service/Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Copy shared modules
COPY common /app/common

# Copy service-specific code
COPY services/whatsapp_service/app /app/app

# Install dependencies
COPY requirements/whatsapp.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Set PYTHONPATH
ENV PYTHONPATH=/app/common

# Run the bot
CMD ["python", "-m", "app.main"]