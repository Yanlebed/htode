# services/telegram_service/app/bot.py

import logging
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os

# Читання токена зі змінних оточення
TELEGRAM_TOKEN = '7937900638:AAHgA0BxbsxGjq7GDDLkMjtizPY8PwyevVM'

# Ініціалізація бота та диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Налаштування логування
logging.basicConfig(level=logging.INFO)

