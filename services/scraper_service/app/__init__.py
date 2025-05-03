# services/scraper_service/app/__init__.py
from common.utils.logging_config import setup_logging

# Initialize service-wide logger
logger = setup_logging('scraper_service', log_level='INFO', log_format='json')
