# services/telegram_service/app/bot.py

import logging
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.utils.exceptions import (
    MessageNotModified, CantParseEntities, NetworkError, RetryAfter,
    BadRequest, Unauthorized, InvalidQueryID, TelegramAPIError,
    MessageToDeleteNotFound, BotBlocked
)
from common.config import TELEGRAM_TOKEN, REDIS_URL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Parse Redis URL for host and port
# REDIS_URL format: redis://localhost:6379/0
import urllib.parse
parsed_redis_url = urllib.parse.urlparse(REDIS_URL)
REDIS_HOST = parsed_redis_url.hostname or "redis"
REDIS_PORT = parsed_redis_url.port or 6379

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_TOKEN)
storage = RedisStorage2(host=REDIS_HOST, port=REDIS_PORT, db=1, prefix='fsm')
dp = Dispatcher(bot, storage=storage)