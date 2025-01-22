# services/telegram_service/app/bot.py

import logging
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os

# Чтение токена из переменных окружения
TELEGRAM_TOKEN = '7937900638:AAHgA0BxbsxGjq7GDDLkMjtizPY8PwyevVM'

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

