"""
Клавиатуры бота.
"""
from .user_keyboards import (
    get_main_menu_kb,
    get_heartbeat_kb,
    get_disclaimer_kb,
    get_wallet_connect_kb,
)
from .board_keyboards import (
    get_levels_kb,
    get_board_detail_kb,
    get_boards_list_kb,
    get_confirm_join_kb,
    get_payment_kb,
)

__all__ = [
    # User
    "get_main_menu_kb",
    "get_heartbeat_kb",
    "get_disclaimer_kb",
    "get_wallet_connect_kb",
    # Board
    "get_levels_kb",
    "get_board_detail_kb",
    "get_boards_list_kb",
    "get_confirm_join_kb",
    "get_payment_kb",
]
