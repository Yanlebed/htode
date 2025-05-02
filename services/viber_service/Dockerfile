# services/viber_service/Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Copy shared modules
COPY common /app/common

# Copy service-specific code
COPY services/viber_service/app /app/app

# Install dependencies
COPY requirements/viber.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt uvicorn fastapi

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]