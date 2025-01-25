# services/telegram_service/app/states.py

from aiogram.dispatcher.filters.state import State, StatesGroup


class FilterStates(StatesGroup):
    waiting_for_property_type = State()
    waiting_for_city = State()
    waiting_for_rooms = State()
    waiting_for_price = State()
    waiting_for_basic_params = State()
    waiting_for_confirmation = State()


class AdvancedFilterStates(StatesGroup):
    waiting_for_floor_max = State()
    waiting_for_first_floor = State()
    waiting_for_last_floor = State()
    waiting_for_pets_allowed = State()
    waiting_for_without_broker = State()
    waiting_for_advanced_confirmation = State()
