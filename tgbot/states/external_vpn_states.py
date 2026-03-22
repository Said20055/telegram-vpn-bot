from aiogram.fsm.state import State, StatesGroup


class ExternalVpnFSM(StatesGroup):
    waiting_url = State()          # ожидаем URL подписки
    waiting_name = State()         # ожидаем название источника
    selecting_servers = State()    # выбираем серверы из списка
    waiting_raw_configs = State()  # ожидаем raw-конфиги (vless://, vmess://, ...)
