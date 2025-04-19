# services/viber_service/app/bot.py

import logging
import os
from viberbot import Api
from viberbot.api.bot_configuration import BotConfiguration
from common.utils.state_manager import RedisStateManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Get Viber token from environment
VIBER_TOKEN = os.getenv("VIBER_TOKEN")
if not VIBER_TOKEN:
    logger.error("VIBER_TOKEN not set in environment variables")
    raise ValueError("VIBER_TOKEN environment variable is required")

# Set your webhook URL - must be HTTPS
WEBHOOK_URL = os.getenv("VIBER_WEBHOOK_URL", "https://your-domain.com/viber/webhook")

# Initialize Viber bot
viber = Api(BotConfiguration(
    name='YourBotName',
    avatar='https://your-domain.com/bot-avatar.jpg',
    auth_token=VIBER_TOKEN
))

# Initialize Redis state manager
state_manager = RedisStateManager(prefix='viber_state')