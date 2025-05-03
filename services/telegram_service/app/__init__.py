# services/telegram_service/app/__init__.py

# Initialize bot first
from .bot import bot

# Configure messaging service
from common.messaging.service import messaging_service
from common.messaging.telegram_messaging import TelegramMessaging
messaging_service.register_messenger("telegram", TelegramMessaging(bot))

# Now import tasks after the service is configured
from . import tasks