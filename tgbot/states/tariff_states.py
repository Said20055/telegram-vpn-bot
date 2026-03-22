from aiogram.fsm.state import State, StatesGroup


class TariffFSM(StatesGroup):
    add_name = State()
    add_price = State()
    add_duration = State()
    edit_field = State()
