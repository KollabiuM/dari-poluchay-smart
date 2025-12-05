"""
Тексты сообщений бота.
"""
from .messages import (
    get_welcome_message,
    get_welcome_back_message,
    get_blocked_message,
    get_dormant_warning_message,
    get_ban_message,
    get_wallet_connected_message,
    get_referral_registered_message,
    get_gift_received_message,
    get_gift_sent_message,
    get_not_registered_message,
)
from .board_messages import (
    get_levels_message,
    get_no_boards_message,
    get_boards_list_message,
    get_board_detail_message,
    get_join_success_message,
    get_join_error_message,
)

__all__ = [
    # User messages
    "get_welcome_message",
    "get_welcome_back_message",
    "get_blocked_message",
    "get_dormant_warning_message",
    "get_ban_message",
    "get_wallet_connected_message",
    "get_referral_registered_message",
    "get_gift_received_message",
    "get_gift_sent_message",
    "get_not_registered_message",
    # Board messages
    "get_levels_message",
    "get_no_boards_message",
    "get_boards_list_message",
    "get_board_detail_message",
    "get_join_success_message",
    "get_join_error_message",
]
