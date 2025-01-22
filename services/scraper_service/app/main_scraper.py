# services/scraper_service/app/fallback.py

import requests
from .fallback import fetch_with_fallback
from common.utils.logger import logger

def do_scrape():
    """
    Вызывает fallback, парсит JSON, формирует список dict {external_id, price, ...}.
    """
    data = fetch_with_fallback()
    if not data:
        logger.warning("Fallback returned no data")
        return []

    results = []
    # Предположим, 'data' - словарь с ключом "data"
    for item in data.get("data", []):
        results.append({
            "external_id": str(item["id"]),
            "price": item.get("price", 0),
            "title": item.get("header", ""),
            "rooms_count": item.get("room_count", 1),
            "city": "Киев",
            "insert_time": item.get("insert_time"),
        })
    return results
