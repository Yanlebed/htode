# services/telegram_service/app/main.py

from aiogram import executor
from .bot import dp
from .handlers import menu_handlers, basic_handlers, advanced_handlers, subscription, support, favorites
# Import the flow integration
from .flow_integration import check_and_process_flow, flow_message_handler
# Import the error handler
from . import error_handler

# Import service logger instead of configuring local logging
from .. import logger

def setup_handlers():
    """
    Make sure all handlers are registered properly.
    This function doesn't need to do anything explicit since imports
    already register the handlers with the dispatcher.
    """
    # The imports above already register the handlers with the dispatcher
    # We're just making sure the error_handler module is initialized
    # and that flow integration is imported so its handlers are registered
    logger.info("All handlers and error handler registered")
    logger.info("Flow integration initialized")

def main():
    """
    Start the Telegram bot (using long polling)
    """
    logger.info("Starting Telegram bot...")
    # Make sure handlers are set up before starting
    setup_handlers()
    executor.start_polling(dp, skip_updates=True)
    logger.info("Bot stopped")

if __name__ == "__main__":
    main()