"""
Клавиатуры для пользователя.
Reply и Inline клавиатуры.
"""
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def get_main_menu_kb() -> ReplyKeyboardMarkup:
    """
    Главное меню бота.
    
    Структура:
    - Левый столбец: 🫶 О нас, 📄 Инструкции, 🔰 Мой статус
    - Правый столбец: 📋 Мои доски, 👋 Приглашение, 🛠️ Инструменты
    - Внизу: ✅ Я тут!, 💼 Кошелёк
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🫶 О нас"),
                KeyboardButton(text="📋 Мои доски"),
            ],
            [
                KeyboardButton(text="📄 Инструкции"),
                KeyboardButton(text="👋 Приглашение"),
            ],
            [
                KeyboardButton(text="🔰 Мой статус"),
                KeyboardButton(text="🛠️ Инструменты"),
            ],
            [
                KeyboardButton(text="✅ Я тут!"),
                KeyboardButton(text="💼 Кошелёк"),
            ],
        ],
        resize_keyboard=True,
    )
    return keyboard


def get_heartbeat_kb() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой 'Я тут'."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Я тут!")],
        ],
        resize_keyboard=True,
    )
    return keyboard


def get_disclaimer_kb() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения Disclaimer."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принимаю правила",
                    callback_data="accept_disclaimer",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 Прочитать правила",
                    url="https://example.com/rules",
                ),
            ],
        ]
    )
    return keyboard


def get_wallet_connect_kb() -> InlineKeyboardMarkup:
    """Клавиатура для подключения кошелька."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💼 Подключить TON Wallet",
                    callback_data="connect_wallet",
                ),
            ],
        ]
    )
    return keyboard


def get_board_actions_kb(board_id: int) -> InlineKeyboardMarkup:
    """Клавиатура действий на доске."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💸 Отправить подарок",
                    callback_data=f"send_gift:{board_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=f"view_board:{board_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 К уровням",
                    callback_data="back_to_levels",
                ),
            ],
        ]
    )
    return keyboard


def get_upgrade_kb(level: int) -> InlineKeyboardMarkup:
    """Клавиатура для апгрейда на следующий уровень."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Активировать",
                    callback_data=f"upgrade:{level}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏳ Подождать авто-апгрейд",
                    callback_data="wait_upgrade",
                ),
            ],
        ]
    )
    return keyboard
