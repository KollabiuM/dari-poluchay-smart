"""
Обработчики команд для досок.
/boards, /join, /board, кнопки действий.
"""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery

from database import AsyncSessionLocal
from services.table_service import TableService, JoinResult
from services.user_service import UserService
from models.table import LEVELS, TableStatus
from keyboards.board_keyboards import (
    get_levels_kb,
    get_board_detail_kb,
    get_boards_list_kb,
    get_confirm_join_kb,
)
from texts.board_messages import (
    get_boards_list_message,
    get_board_detail_message,
    get_join_success_message,
    get_join_error_message,
    get_no_boards_message,
    get_levels_message,
)
from utils.send_message_utils import alert

router = Router(name="boards")
logger = logging.getLogger(__name__)


# ===========================================
# КОМАНДЫ
# ===========================================

@router.message(Command("boards"))
@router.message(F.text == "📋 Мои доски")
async def cmd_boards(message: Message) -> None:
    """Показать все доски пользователя с суммарной статистикой."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        user_service = UserService(session)
        
        user = await user_service.get_by_tid(tid)
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        # Получаем все доски пользователя (не только активные)
        all_tables = await table_service.get_user_tables(tid, active_only=False)
        
        # Маппинг английских названий на русские
        level_names_ru = {
            1: "Стартовая",
            2: "Оловянная",
            3: "Бронзовая",
            4: "Медная",
            5: "Серебряная",
            6: "Янтарная",
            7: "Золотая",
            8: "Рубиновая",
            9: "Платиновая",
            10: "Изумрудная",
            11: "Бриллиантовая",
            12: "Сапфировая",
            13: "Титановая",
        }
        
        # Группируем доски по уровням и считаем подарки
        level_stats = {}  # {level: {"gifts_received": количество, "user_on_level": bool}}
        
        for level in range(1, 14):
            level_stats[level] = {
                "gifts_received": 0,  # Количество полученных подарков (не сумма!)
                "user_on_level": False,
            }
        
        # Определяем максимальный уровень, на котором пользователь находится
        max_user_level = 0
        
        for table in all_tables:
            level = table.level
            # Считаем количество полученных подарков на этой доске
            level_stats[level]["gifts_received"] += table.gifts_received
            
            # Проверяем, находится ли пользователь на этой доске
            position = await table_service.get_user_position(table, tid)
            if position:
                level_stats[level]["user_on_level"] = True
                if level > max_user_level:
                    max_user_level = level
        
        # Определяем доступные уровни:
        # ✅ Доступны: уровни, на которых пользователь уже есть + следующий после максимального
        # ❌ Недоступны: остальные уровни
        available_levels = set()
        for level in range(1, 14):
            if level_stats[level]["user_on_level"]:
                available_levels.add(level)
        
        # Добавляем следующий уровень после максимального (если не Titan)
        if max_user_level > 0 and max_user_level < 13:
            next_level = max_user_level + 1
            available_levels.add(next_level)
        
        # Считаем суммарное количество полученных подарков (в рублях)
        # Конвертируем USDT в рубли (примерно 1 USDT = 100₽)
        USDT_TO_RUB = 100
        total_gifts_rub = 0
        
        for level in range(1, 14):
            level_info = LEVELS.get(level, {})
            gift_amount_usdt = level_info.get("amount", 0)
            gifts_count = level_stats[level]["gifts_received"]
            # Сумма = количество подарков * номинал подарка * курс
            total_gifts_rub += gifts_count * gift_amount_usdt * USDT_TO_RUB
        
        # Формируем сообщение
        lines = []
        
        # Заголовок с суммарным количеством подарков
        lines.append(f"🎁 <b>Ваши подарки: {total_gifts_rub:,}₽</b>\n")
        
        # Список досок снизу вверх (от Start к Titan)
        for level in range(1, 14):
            level_name_ru = level_names_ru.get(level, f"Уровень {level}")
            gifts_received = level_stats[level]["gifts_received"]
            
            # Определяем иконку доступности
            if level in available_levels:
                icon = "✅"
            else:
                icon = "❌"
            
            # Формируем строку: ✅/❌ Название доски (количество полученных подарков)
            # В скобках показываем сумму в рублях (количество * номинал * курс)
            level_info = LEVELS.get(level, {})
            gift_amount_usdt = level_info.get("amount", 0)
            gifts_amount_rub = gifts_received * gift_amount_usdt * USDT_TO_RUB
            
            lines.append(
                f"{icon} <b>{level_name_ru} доска</b> ({gifts_amount_rub:,}₽)"
            )
        
        text = "\n".join(lines)
        
        await message.answer(
            text,
            parse_mode="HTML",
        )


@router.message(Command("levels"))
@router.message(F.text == "🎯 Уровни")
async def cmd_levels(message: Message) -> None:
    """Показать все уровни досок."""
    if not message.from_user:
        return
    
    text = get_levels_message()
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_levels_kb(),
    )


@router.message(Command("join"))
async def cmd_join(message: Message, command: CommandObject) -> None:
    """
    Войти на доску уровня.
    Использование: /join <level> или /join <level_name>
    Примеры: /join 1, /join start, /join bronze
    """
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    if not command.args:
        await message.answer(
            "📋 <b>Использование:</b>\n"
            "<code>/join 1</code> — войти на Start (10$)\n"
            "<code>/join 3</code> — войти на Bronze (40$)\n\n"
            "Или выберите уровень:",
            parse_mode="HTML",
            reply_markup=get_levels_kb(),
        )
        return
    
    # Парсим уровень
    level = parse_level(command.args.strip())
    
    if not level:
        await message.answer(
            f"❌ Неверный уровень: {command.args}\n\n"
            "Используйте число 1-13 или название (start, bronze, gold...)",
            parse_mode="HTML",
        )
        return
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        user_service = UserService(session)
        
        user = await user_service.get_by_tid(tid)
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        # Проверяем можно ли присоединиться
        can_join, reason = await table_service.can_user_join(tid, level)
        
        if not can_join:
            await message.answer(
                get_join_error_message(reason, level),
                parse_mode="HTML",
            )
            return
        
        # Ищем подходящую доску
        table, search_reason = await table_service.find_table_for_user(tid, level)
        
        if not table:
            await message.answer(
                f"😔 <b>Нет доступных досок</b>\n\n"
                f"Уровень: {LEVELS[level]['name']} ({LEVELS[level]['amount']}$)\n"
                f"Причина: {search_reason}\n\n"
                f"Попробуйте позже или создайте свою доску.",
                parse_mode="HTML",
            )
            return
        
        # Показываем подтверждение
        level_info = LEVELS[level]
        
        await message.answer(
            f"🎯 <b>Найдена доска!</b>\n\n"
            f"Уровень: <b>{level_info['name']}</b>\n"
            f"Сумма подарка: <b>{level_info['amount']} USDT</b>\n"
            f"Доска: #{table.id}\n"
            f"Свободных мест: {table.empty_slots_total}\n"
            f"Найдена через: {search_reason}\n\n"
            f"⏰ После входа у вас будет 72 часа на оплату.",
            parse_mode="HTML",
            reply_markup=get_confirm_join_kb(table.id, level),
        )


@router.message(Command("board"))
async def cmd_board(message: Message, command: CommandObject) -> None:
    """
    Показать детали доски.
    Использование: /board <id>
    """
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    if not command.args or not command.args.isdigit():
        await message.answer(
            "📋 <b>Использование:</b>\n"
            "<code>/board 123</code> — показать доску #123",
            parse_mode="HTML",
        )
        return
    
    table_id = int(command.args)
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        table = await table_service.get_by_id(table_id)
        
        if not table:
            await message.answer(f"❌ Доска #{table_id} не найдена")
            return
        
        position = await table_service.get_user_position(table, tid)
        text = await get_board_detail_message(table, table_service, tid)
        
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_board_detail_kb(table, position),
        )


# ===========================================
# CALLBACK HANDLERS
# ===========================================

@router.callback_query(F.data.startswith("join_level:"))
async def callback_join_level(callback: CallbackQuery) -> None:
    """Выбор уровня для входа."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    level = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        # Проверяем можно ли
        can_join, reason = await table_service.can_user_join(tid, level)
        
        if not can_join:
            await callback.answer(get_join_error_message(reason, level), show_alert=True)
            return
        
        # Ищем доску
        table, search_reason = await table_service.find_table_for_user(tid, level)
        
        if not table:
            await callback.answer("😔 Нет доступных досок", show_alert=True)
            return
        
        level_info = LEVELS[level]
        
        await callback.message.edit_text(
            f"🎯 <b>Найдена доска!</b>\n\n"
            f"Уровень: <b>{level_info['name']}</b>\n"
            f"Сумма подарка: <b>{level_info['amount']} USDT</b>\n"
            f"Доска: #{table.id}\n"
            f"Свободных мест: {table.empty_slots_total}\n\n"
            f"⏰ После входа у вас будет 72 часа на оплату.",
            parse_mode="HTML",
            reply_markup=get_confirm_join_kb(table.id, level),
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_join:"))
async def callback_confirm_join(callback: CallbackQuery) -> None:
    """Подтверждение входа на доску."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    table_id = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        success, reason, slot = await table_service.join_table(table_id, tid)
        
        if not success:
            await callback.answer(f"❌ {reason}", show_alert=True)
            return
        
        table = await table_service.get_by_id(table_id)
        position_name = await table_service.get_position_name(slot)
        
        await callback.message.edit_text(
            get_join_success_message(table, slot, position_name),
            parse_mode="HTML",
            reply_markup=get_board_detail_kb(table, slot),
        )
    
    await callback.answer("✅ Вы заняли место!")


@router.callback_query(F.data.startswith("view_board:"))
async def callback_view_board(callback: CallbackQuery) -> None:
    """Просмотр деталей доски."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    table_id = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        table = await table_service.get_by_id(table_id)
        
        if not table:
            await callback.answer("❌ Доска не найдена", show_alert=True)
            return
        
        position = await table_service.get_user_position(table, tid)
        text = await get_board_detail_message(table, table_service, tid)
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_board_detail_kb(table, position),
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("leave_board:"))
async def callback_leave_board(callback: CallbackQuery) -> None:
    """Покинуть доску."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    table_id = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        success, reason = await table_service.leave_table(table_id, tid)
        
        if not success:
            error_messages = {
                "TABLE_NOT_FOUND": "Доска не найдена",
                "ALREADY_PAID": "Нельзя покинуть после оплаты",
                "NOT_A_DONOR": "Вы не даритель на этой доске",
            }
            msg = error_messages.get(reason, reason)
            await callback.answer(f"❌ {msg}", show_alert=True)
            return
        
        await callback.message.edit_text(
            f"✅ <b>Вы покинули доску #{table_id}</b>\n\n"
            f"Место освобождено для другого участника.",
            parse_mode="HTML",
        )
    
    await callback.answer("✅ Вы покинули доску")


@router.callback_query(F.data == "back_to_levels")
async def callback_back_to_levels(callback: CallbackQuery) -> None:
    """Вернуться к списку уровней."""
    text = get_levels_message()
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_levels_kb(),
    )
    
    await callback.answer()


@router.callback_query(F.data == "back_to_boards")
async def callback_back_to_boards(callback: CallbackQuery) -> None:
    """Вернуться к списку досок."""
    if not callback.from_user:
        return
    
    tid = callback.from_user.id
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        tables = await table_service.get_user_tables(tid, active_only=True)
        
        if not tables:
            await callback.message.edit_text(
                get_no_boards_message(),
                parse_mode="HTML",
                reply_markup=get_levels_kb(),
            )
        else:
            text = await get_boards_list_message(tables, table_service, tid)
            
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_boards_list_kb(tables),
            )
    
    await callback.answer()


@router.callback_query(F.data.startswith("split_board:"))
async def callback_split_board(callback: CallbackQuery) -> None:
    """Разделить доску на левую или правую сторону."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    
    # Парсим данные: split_board:table_id:side
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("❌ Неверный формат команды", show_alert=True)
        return
    
    try:
        table_id = int(parts[1])
        side = parts[2]  # 'left' или 'right'
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка парсинга данных", show_alert=True)
        return
    
    if side not in ["left", "right"]:
        await callback.answer("❌ Неверная сторона (должно быть left или right)", show_alert=True)
        return
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        user_service = UserService(session)
        
        # Проверяем что пользователь — получатель на этой доске
        table = await table_service.get_by_id(table_id)
        if not table:
            await callback.answer("❌ Доска не найдена", show_alert=True)
            return
        
        if table.rec != tid:
            await callback.answer("❌ Только получатель может разделить доску", show_alert=True)
            return
        
        # Проверяем готовность стороны
        if side == "left" and not table.can_split_left:
            await callback.answer("❌ Левая сторона ещё не готова к разделению", show_alert=True)
            return
        if side == "right" and not table.can_split_right:
            await callback.answer("❌ Правая сторона ещё не готова к разделению", show_alert=True)
            return
        
        # Разделяем доску
        try:
            success, reason, new_table = await table_service.split_table(table_id, side)
            
            if not success:
                await callback.answer(f"❌ Ошибка: {reason}", show_alert=True)
                return
        except Exception as e:
            logger.error(f"Ошибка при разделении доски #{table_id}: {e}", exc_info=True)
            await alert(f"Ошибка при разделении доски table_id={table_id} user={tid}: {e}")
            await callback.answer("❌ Произошла ошибка при разделении доски", show_alert=True)
            return
        
        level_info = LEVELS.get(table.level, {})
        level_name = level_info.get("name", f"L{table.level}")
        
        # Обновляем сообщение
        text = (
            f"✂️ <b>Доска разделена!</b>\n\n"
            f"Родительская доска: <b>#{table_id}</b>\n"
            f"Новая доска: <b>#{new_table.id}</b>\n"
            f"Уровень: <b>{level_name}</b>\n"
            f"Сторона: <b>{side}</b>\n\n"
            f"🎉 Новая доска создана и готова к заполнению!"
        )
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_board_detail_kb(table, "rec"),
        )
        
        await callback.answer("✅ Доска успешно разделена!")
        
        logger.info(f"Доска #{table_id} разделена на сторону {side}, создана доска #{new_table.id}")


# ===========================================
# УТИЛИТЫ
# ===========================================

def parse_level(arg: str) -> Optional[int]:
    """
    Парсит уровень из строки.
    Принимает: число (1-13) или название (start, bronze, gold...)
    """
    # Пробуем как число
    if arg.isdigit():
        level = int(arg)
        if 1 <= level <= 13:
            return level
        return None
    
    # Пробуем как название
    arg_lower = arg.lower()
    for level_num, info in LEVELS.items():
        if info["name"].lower() == arg_lower:
            return level_num
    
    return None
