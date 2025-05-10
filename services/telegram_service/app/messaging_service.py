# services/telegram_service/app/messaging_service.py
from common.messaging.service import MessagingService
from common.messaging.telegram_messaging import TelegramMessaging
from .bot import bot
from . import logger

# Create and register telegram messaging service
messaging_service = MessagingService.create_for_service('telegram')
messaging_service.register_messenger("telegram", TelegramMessaging(bot))
logger.info("Telegram messaging service registered")