"""
Клавиатуры для работы с досками.
"""
from typing import List, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from models.table import Table, LEVELS


def get_levels_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора уровня для входа."""
    buttons = []
    
    # Первые 6 уровней (доступные)
    row1 = []
    for level in [1, 2, 3]:
        info = LEVELS[level]
        row1.append(InlineKeyboardButton(
            text=f"{info['name']} ({info['amount']}$)",
            callback_data=f"join_level:{level}",
        ))
    buttons.append(row1)
    
    row2 = []
    for level in [4, 5, 6]:
        info = LEVELS[level]
        row2.append(InlineKeyboardButton(
            text=f"{info['name']} ({info['amount']}$)",
            callback_data=f"join_level:{level}",
        ))
    buttons.append(row2)
    
    # Высокие уровни
    row3 = []
    for level in [7, 8, 9]:
        info = LEVELS[level]
        row3.append(InlineKeyboardButton(
            text=f"{info['name']} ({info['amount']}$)",
            callback_data=f"join_level:{level}",
        ))
    buttons.append(row3)
    
    row4 = []
    for level in [10, 11]:
        info = LEVELS[level]
        row4.append(InlineKeyboardButton(
            text=f"{info['name']} ({info['amount']}$)",
            callback_data=f"join_level:{level}",
        ))
    buttons.append(row4)
    
    row5 = []
    for level in [12, 13]:
        info = LEVELS[level]
        row5.append(InlineKeyboardButton(
            text=f"💎 {info['name']} ({info['amount']}$)",
            callback_data=f"join_level:{level}",
        ))
    buttons.append(row5)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_boards_list_kb(tables: List[Table]) -> InlineKeyboardMarkup:
    """Клавиатура списка досок пользователя."""
    buttons = []
    
    for table in tables[:10]:  # Максимум 10 досок
        level_info = LEVELS.get(table.level, {})
        level_name = level_info.get("name", f"L{table.level}")
        
        # Иконка статуса
        if table.status == "closed":
            icon = "✅"
        elif table.gifts_received >= 4:
            icon = "🔥"
        else:
            icon = "📊"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {level_name} #{table.id} ({table.gifts_received}/8)",
                callback_data=f"view_board:{table.id}",
            )
        ])
    
    # Кнопка добавления новой доски
    buttons.append([
        InlineKeyboardButton(
            text="➕ Войти на новую доску",
            callback_data="back_to_levels",
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_board_detail_kb(
    table: Table,
    user_position: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Клавиатура деталей доски."""
    buttons = []
    
    # Если пользователь — даритель и ещё не оплатил
    if user_position and user_position.startswith('d'):
        is_paid = getattr(table, f"{user_position}_pay", False)
        
        if not is_paid:
            buttons.append([
                InlineKeyboardButton(
                    text="💸 Отправить подарок",
                    callback_data=f"send_gift:{table.id}",
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="❌ Покинуть доску",
                    callback_data=f"leave_board:{table.id}",
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text="✅ Подарок отправлен",
                    callback_data="noop",
                )
            ])
    
    # Если получатель — показываем статистику
    if user_position == 'rec':
        buttons.append([
            InlineKeyboardButton(
                text=f"🎁 Получено: {table.gifts_received}/8",
                callback_data="noop",
            )
        ])
        
        # Кнопки разделения если готово
        if table.can_split_left:
            buttons.append([
                InlineKeyboardButton(
                    text="✂️ Разделить левую сторону",
                    callback_data=f"split_board:{table.id}:left",
                )
            ])
        if table.can_split_right:
            buttons.append([
                InlineKeyboardButton(
                    text="✂️ Разделить правую сторону",
                    callback_data=f"split_board:{table.id}:right",
                )
            ])
    
    # Навигация
    buttons.append([
        InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data=f"view_board:{table.id}",
        ),
        InlineKeyboardButton(
            text="◀️ Мои доски",
            callback_data="back_to_boards",
        ),
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirm_join_kb(table_id: int, level: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения входа на доску."""
    level_info = LEVELS.get(level, {})
    amount = level_info.get("amount", 0)
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Войти ({amount} USDT)",
                    callback_data=f"confirm_join:{table_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Выбрать другой уровень",
                    callback_data="back_to_levels",
                )
            ],
        ]
    )


def get_payment_kb(table_id: int, amount: int, receiver_wallet: str) -> InlineKeyboardMarkup:
    """Клавиатура для оплаты подарка."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💳 Оплатить {amount} USDT",
                    callback_data=f"pay_gift:{table_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Скопировать адрес",
                    callback_data=f"copy_wallet:{table_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил",
                    callback_data=f"confirm_paid:{table_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=f"view_board:{table_id}",
                )
            ],
        ]
    )
