# services/telegram_service/app/main.py

import logging
from aiogram import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from .bot import dp
from . import handlers  # Реєстрація хендлерів
from aiogram.dispatcher import Dispatcher

# Налаштування логування
logging.basicConfig(level=logging.INFO)

def main():
    # Запускаємо бота (long polling)
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    main()
