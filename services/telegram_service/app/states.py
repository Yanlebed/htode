# services/telegram_service/app/states.py

from aiogram.dispatcher.filters.state import State, StatesGroup

class FilterStates(StatesGroup):
    waiting_for_property_type = State()
    waiting_for_city = State()
    waiting_for_rooms = State()
    waiting_for_price = State()
    waiting_for_listing_date = State()
    waiting_for_confirmation = State()
