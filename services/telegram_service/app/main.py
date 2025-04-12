# services/telegram_service/app/main.py

import logging
from aiogram import executor
from .bot import dp
from .handlers import menu_handlers, basic_handlers, advanced_handlers, subscription, support, favorites  # Реєстрація хендлерів

# Налаштування логування
logging.basicConfig(level=logging.INFO)


def main():
    # Запускаємо бота (long polling)
    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    main()
