# services/viber_service/app/bot.py

import os
from viberbot import Api
from viberbot.api.bot_configuration import BotConfiguration
from common.unified_state_management import state_manager

# Import the service logger
from . import logger

# Get Viber token from environment
VIBER_TOKEN = os.getenv("VIBER_TOKEN")
if not VIBER_TOKEN:
    logger.error("VIBER_TOKEN not set in environment variables")
    raise ValueError("VIBER_TOKEN environment variable is required")

# Set your webhook URL - must be HTTPS
WEBHOOK_URL = os.getenv("VIBER_WEBHOOK_URL", "https://your-domain.com/viber/webhook")

logger.info("Initializing Viber bot", extra={
    'webhook_url': WEBHOOK_URL,
    'token_present': bool(VIBER_TOKEN)
})

# Initialize Viber bot
try:
    viber = Api(BotConfiguration(
        name='YourBotName',
        avatar='https://your-domain.com/bot-avatar.jpg',
        auth_token=VIBER_TOKEN
    ))
    logger.info("Viber bot initialized successfully")
except Exception as e:
    logger.error("Failed to initialize Viber bot", exc_info=True, extra={
        'error_type': type(e).__name__
    })
    raise

# Initialize Redis state manager
try:
    state_manager.register_platform_handler('viber', viber)
    logger.info("Registered Viber platform handler with state manager")
except Exception as e:
    logger.error("Failed to register Viber platform handler", exc_info=True, extra={
        'error_type': type(e).__name__
    })
    raise

# Register Viber messenger with the messaging service
try:
    from common.messaging.viber_messaging import ViberMessaging
    from common.messaging.service import MessagingService

    # Create service-specific messaging service
    messaging_service = MessagingService.create_for_service('viber')
    logger.info("Viber messaging service created successfully")
except Exception as e:
    logger.error("Failed to create Viber messaging service", exc_info=True, extra={
        'error_type': type(e).__name__
    })
    raise