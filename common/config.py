import os

# Можно читать ENV или .env
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "myuser")
DB_PASS = os.getenv("DB_PASS", "mypass")
DB_NAME = os.getenv("DB_NAME", "mydb")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

SCRAPE_URL = os.getenv("SCRAPE_URL", "https://example.com/api/realties")
