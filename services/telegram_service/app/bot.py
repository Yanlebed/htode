# services/telegram_service/app/bot.py

import logging
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2
import os

# Читання токена зі змінних оточення
TELEGRAM_TOKEN = '7937900638:AAHgA0BxbsxGjq7GDDLkMjtizPY8PwyevVM'
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")

# Ініціалізація бота та диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
# storage = MemoryStorage()
storage = RedisStorage2(host=REDIS_HOST, port=REDIS_PORT, db=1, prefix='fsm')
dp = Dispatcher(bot, storage=storage)

# Налаштування логування
logging.basicConfig(level=logging.INFO)

