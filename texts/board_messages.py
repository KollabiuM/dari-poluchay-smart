"""
Тексты сообщений о досках.
"""
from typing import List, Optional
from models.table import Table, LEVELS, TableStatus


def get_levels_message() -> str:
    """Сообщение со списком уровней."""
    lines = ["🎯 <b>Уровни досок</b>\n"]
    
    for level, info in LEVELS.items():
        emoji = "💎" if level >= 10 else "🔹" if level >= 5 else "▫️"
        lines.append(f"{emoji} <b>{info['name']}</b> — {info['amount']} USDT")
    
    lines.append("\n💡 Выберите уровень для входа:")
    
    return "\n".join(lines)


def get_no_boards_message() -> str:
    """Сообщение когда нет активных досок."""
    return """📊 <b>Мои доски</b>

У вас пока нет активных досок.

💡 <b>Как начать?</b>
1. Выберите уровень ниже
2. Система найдёт подходящую доску
3. Отправьте подарок получателю
4. Ждите своей очереди стать получателем!

Выберите уровень для входа:"""


async def get_boards_list_message(
    tables: List[Table],
    table_service,
    user_tid: int,
) -> str:
    """Сообщение со списком досок пользователя."""
    lines = [f"📊 <b>Мои доски ({len(tables)})</b>\n"]
    
    for table in tables:
        level_info = LEVELS.get(table.level, {})
        level_name = level_info.get("name", f"L{table.level}")
        amount = level_info.get("amount", 0)
        
        # Определяем позицию пользователя
        position = await table_service.get_user_position(table, user_tid)
        position_name = await table_service.get_position_name(position) if position else "?"
        
        # Статус
        if table.status == TableStatus.CLOSED.value:
            status = "✅ Завершена"
        elif table.gifts_received >= 4:
            status = f"🔥 {table.gifts_received}/8 подарков"
        else:
            status = f"⏳ {table.gifts_received}/8 подарков"
        
        lines.append(
            f"<b>#{table.id} {level_name}</b> ({amount}$)\n"
            f"   {position_name}\n"
            f"   {status}\n"
        )
    
    lines.append("\n👇 Нажмите на доску для деталей")
    
    return "\n".join(lines)


async def get_board_detail_message(
    table: Table,
    table_service,
    user_tid: int,
) -> str:
    """Детальное сообщение о доске."""
    level_info = LEVELS.get(table.level, {})
    level_name = level_info.get("name", f"L{table.level}")
    amount = level_info.get("amount", 0)
    
    # Позиция пользователя
    position = await table_service.get_user_position(table, user_tid)
    position_name = await table_service.get_position_name(position) if position else "Не на доске"
    
    # Статус доски
    if table.status == TableStatus.CLOSED.value:
        status = "✅ Завершена"
    elif table.status == TableStatus.SPLITTING.value:
        status = "✂️ Разделяется"
    elif table.gifts_received >= 4:
        status = "🔥 Активная"
    else:
        status = "⏳ Ожидание"
    
    lines = [
        f"📊 <b>Доска #{table.id}</b>\n",
        f"🎯 Уровень: <b>{level_name}</b> ({amount} USDT)",
        f"📍 Ваша роль: <b>{position_name}</b>",
        f"📈 Статус: {status}",
        f"🎁 Подарков: <b>{table.gifts_received}/8</b>",
        "",
    ]
    
    # Визуализация доски
    lines.append("┌─────── Структура ───────┐")
    lines.append(f"│       {'🟢' if table.rec else '⚫'} REC            │")
    lines.append(f"│      /     \\           │")
    lines.append(f"│   {'🟢' if table.crl else '⚫'}CR     CR{'🟢' if table.crr else '⚫'}       │")
    lines.append(f"│   / \\     / \\          │")
    lines.append(f"│ {'🟢' if table.stl1 else '⚫'}ST ST{'🟢' if table.stl2 else '⚫'} {'🟢' if table.str3 else '⚫'}ST ST{'🟢' if table.str4 else '⚫'}   │")
    
    # Дарители с оплатой
    d1 = "✅" if table.dl1_pay else ("🟡" if table.dl1 else "⚫")
    d2 = "✅" if table.dl2_pay else ("🟡" if table.dl2 else "⚫")
    d3 = "✅" if table.dl3_pay else ("🟡" if table.dl3 else "⚫")
    d4 = "✅" if table.dl4_pay else ("🟡" if table.dl4 else "⚫")
    d5 = "✅" if table.dr5_pay else ("🟡" if table.dr5 else "⚫")
    d6 = "✅" if table.dr6_pay else ("🟡" if table.dr6 else "⚫")
    d7 = "✅" if table.dr7_pay else ("🟡" if table.dr7 else "⚫")
    d8 = "✅" if table.dr8_pay else ("🟡" if table.dr8 else "⚫")
    
    lines.append(f"│{d1}{d2}{d3}{d4}       {d5}{d6}{d7}{d8}│")
    lines.append("└─────────────────────────┘")
    lines.append("")
    lines.append("⚫ пусто  🟡 ждёт оплаты  ✅ оплачено")
    
    # Информация о сторонах
    lines.append("")
    left_paid = sum([table.dl1_pay, table.dl2_pay, table.dl3_pay, table.dl4_pay])
    right_paid = sum([table.dr5_pay, table.dr6_pay, table.dr7_pay, table.dr8_pay])
    
    lines.append(f"◀️ Левая: {left_paid}/4 {'✂️ готово!' if table.can_split_left else ''}")
    lines.append(f"▶️ Правая: {right_paid}/4 {'✂️ готово!' if table.can_split_right else ''}")
    
    # Если пользователь — даритель, показываем дедлайн
    if position and position.startswith('d'):
        deadline = getattr(table, f"{position}_deadline", None)
        is_paid = getattr(table, f"{position}_pay", False)
        
        if deadline and not is_paid:
            import time
            remaining = deadline - int(time.time())
            hours = remaining // 3600
            
            if hours > 0:
                lines.append(f"\n⏰ <b>До оплаты: {hours} ч.</b>")
            else:
                lines.append(f"\n⚠️ <b>Срок истекает!</b>")
    
    return "\n".join(lines)


def get_join_success_message(
    table: Table,
    slot: str,
    position_name: str,
) -> str:
    """Сообщение об успешном входе на доску."""
    level_info = LEVELS.get(table.level, {})
    level_name = level_info.get("name", f"L{table.level}")
    amount = level_info.get("amount", 0)
    
    return f"""✅ <b>Вы вошли на доску!</b>

📊 Доска: <b>#{table.id}</b>
🎯 Уровень: <b>{level_name}</b>
📍 Позиция: <b>{position_name}</b>
💰 Сумма подарка: <b>{amount} USDT</b>

⏰ <b>У вас 72 часа</b> чтобы отправить подарок получателю.

Нажмите "Отправить подарок" чтобы увидеть реквизиты."""


def get_join_error_message(reason: str, level: int) -> str:
    """Сообщение об ошибке входа."""
    level_info = LEVELS.get(level, {})
    level_name = level_info.get("name", f"L{level}")
    
    messages = {
        "USER_ALREADY_ON_LEVEL": (
            f"❌ <b>Вы уже на доске {level_name}</b>\n\n"
            f"Нельзя быть на двух досках одного уровня одновременно.\n"
            f"Завершите текущую доску или выберите другой уровень."
        ),
        "USER_NOT_FOUND": (
            "❌ <b>Пользователь не найден</b>\n\n"
            "Отправьте /start для регистрации."
        ),
        "USER_BLOCKED": (
            "⛔ <b>Ваш аккаунт заблокирован</b>\n\n"
            "Вы не можете входить на доски во время блокировки."
        ),
        "USER_DORMANT": (
            "😴 <b>Вы в статусе 'Спящий'</b>\n\n"
            "Пригласите партнёра и нажмите 'Я тут' чтобы активироваться."
        ),
    }
    
    return messages.get(reason, f"❌ Ошибка: {reason}")
