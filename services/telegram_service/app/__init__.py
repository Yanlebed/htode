# services/telegram_service/app/__init__.py

from common.messaging.service import MessagingService
from common.messaging.telegram_messaging import TelegramMessaging
from .bot import bot
from . import tasks

# Create telegram-specific messaging service
messaging_service = MessagingService()
messaging_service.register_messenger("telegram", TelegramMessaging(bot))