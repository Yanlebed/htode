# For example: services/webapps/Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Copy your requirements (or have a separate file just for the web app).
# Suppose we only need Flask for this minimal example:
RUN pip install --no-cache-dir Flask

# Copy the mini_webapp.py into the container
COPY mini_webapp.py /app/mini_webapp.py

# Expose port 8080 (the Flask port)
EXPOSE 8080

# Launch the Flask server
CMD ["python", "/app/mini_webapp.py"]
