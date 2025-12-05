"""
Обработчики для досок.
Просмотр, вход, детали, генерация картинки.
"""
import logging
from typing import Optional, Dict, List

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command, CommandObject

from database import AsyncSessionLocal
from services.table_service import TableService, JoinResult
from services.user_service import UserService
from services.board_image_service import get_board_image_service
from models.table import LEVELS, Table, TableStatus
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router(name="boards")
logger = logging.getLogger(__name__)


# ===========================================
# КЛАВИАТУРЫ
# ===========================================

def get_levels_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора уровня."""
    buttons = []
    row = []
    for lvl, data in LEVELS.items():
        btn = InlineKeyboardButton(
            text=f"{data['name']} ({data['amount']}$)",
            callback_data=f"select_level:{lvl}"
        )
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_board_detail_kb(table_id: int, user_position: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура деталей доски (как на референсе)."""
    buttons = [
        [InlineKeyboardButton(
            text="🪻 Данные получателя",
            callback_data=f"receiver_info:{table_id}"
        )],
        [InlineKeyboardButton(
            text="👥 Показать команду доски",
            callback_data=f"show_team:{table_id}"
        )],
        [InlineKeyboardButton(
            text="🖼 Показать доску картинкой",
            callback_data=f"show_board_image:{table_id}"
        )],
        [InlineKeyboardButton(
            text="👤 Показать дарителей",
            callback_data=f"show_donors:{table_id}"
        )],
        [InlineKeyboardButton(
            text="🔄 Выбрать другую доску",
            callback_data="back_to_levels"
        )],
    ]
    
    # Если пользователь даритель и не оплатил — добавляем кнопку оплаты
    if user_position and user_position.startswith('d'):
        buttons.insert(0, [InlineKeyboardButton(
            text="💸 Отправить подарок",
            callback_data=f"send_gift:{table_id}"
        )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_kb(table_id: int) -> InlineKeyboardMarkup:
    """Кнопка возврата."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Вернуться", callback_data=f"view_board:{table_id}")]
    ])


# ===========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ===========================================

async def get_user_map(session, table: Table) -> Dict[int, str]:
    """Получить словарь {tid: display_name} для всех участников доски."""
    user_service = UserService(session)
    
    all_tids = [
        table.rec, table.crl, table.crr,
        table.stl1, table.stl2, table.str3, table.str4,
        table.dl1, table.dl2, table.dl3, table.dl4,
        table.dr5, table.dr6, table.dr7, table.dr8
    ]
    all_tids = [t for t in all_tids if t]
    
    user_map = {}
    for tid in all_tids:
        user = await user_service.get_by_tid(tid)
        if user:
            user_map[tid] = user.display_name
        else:
            user_map[tid] = f"ID:{tid}"
    
    return user_map


def get_position_emoji(position: str) -> str:
    """Эмодзи для позиции."""
    emojis = {
        'rec': '🎁',
        'crl': '⭐', 'crr': '⭐',
        'stl1': '🔨', 'stl2': '🔨', 'str3': '🔨', 'str4': '🔨',
        'dl1': '🎀', 'dl2': '🎀', 'dl3': '🎀', 'dl4': '🎀',
        'dr5': '🎀', 'dr6': '🎀', 'dr7': '🎀', 'dr8': '🎀',
    }
    return emojis.get(position, '❓')


def get_position_name_ru(position: str) -> str:
    """Название позиции на русском."""
    names = {
        'rec': 'Получатель',
        'crl': 'Создатель', 'crr': 'Создатель',
        'stl1': 'Строитель', 'stl2': 'Строитель', 
        'str3': 'Строитель', 'str4': 'Строитель',
        'dl1': 'Даритель', 'dl2': 'Даритель', 
        'dl3': 'Даритель', 'dl4': 'Даритель',
        'dr5': 'Даритель', 'dr6': 'Даритель', 
        'dr7': 'Даритель', 'dr8': 'Даритель',
    }
    return names.get(position, 'Участник')


# ===========================================
# КОМАНДЫ
# ===========================================

@router.message(F.text == "📋 Мои доски")
@router.message(Command("boards"))
async def cmd_boards(message: Message):
    """Показать все доски пользователя в виде кнопок."""
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
        
        # Находим доску пользователя для каждого уровня
        user_tables_by_level = {}  # {level: table}
        
        for table in all_tables:
            position = await table_service.get_user_position(table, tid)
            if position:
                # Пользователь находится на этой доске
                level = table.level
                # Сохраняем первую найденную доску на этом уровне
                if level not in user_tables_by_level:
                    user_tables_by_level[level] = table
        
        # Определяем максимальный уровень, на котором пользователь находится
        max_user_level = max(user_tables_by_level.keys()) if user_tables_by_level else 0
        
        # Определяем доступные уровни:
        # ✅ Доступны: уровни, на которых пользователь уже есть + следующий после максимального
        # ❌ Недоступны: остальные уровни
        available_levels = set(user_tables_by_level.keys())
        if max_user_level > 0 and max_user_level < 13:
            next_level = max_user_level + 1
            available_levels.add(next_level)
        
        # Формируем кнопки сверху вниз (от Titan к Start)
        buttons = []
        
        for level in range(13, 0, -1):  # От 13 (Titan) к 1 (Start)
            level_name_ru = level_names_ru.get(level, f"Уровень {level}")
            level_info = LEVELS.get(level, {})
            gift_amount_usdt = level_info.get("amount", 0)
            
            # Определяем иконку доступности
            if level in available_levels:
                icon = "✅"
            else:
                icon = "❌"
            
            # Находим доску пользователя на этом уровне
            user_table = user_tables_by_level.get(level)
            
            if user_table:
                # Пользователь на доске - считаем подарки в USDT
                gifts_received = user_table.gifts_received
                gifts_amount_usdt_total = gifts_received * gift_amount_usdt
                
                button_text = f"{level_name_ru} {icon} ({gifts_amount_usdt_total} USDT)"
                callback_data = f"view_board:{user_table.id}"
            else:
                # Пользователь не на доске
                button_text = f"{level_name_ru} {icon} (0 USDT)"
                # Если уровень доступен (следующий после максимального), можно войти
                if level in available_levels and level == max_user_level + 1:
                    callback_data = f"join_level:{level}"
                else:
                    # Недоступный уровень - показываем информацию
                    callback_data = f"level_info:{level}"
            
            buttons.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=callback_data,
                )
            ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Считаем суммарное количество полученных подарков в USDT
        total_gifts_usdt = 0
        for level, table in user_tables_by_level.items():
            level_info = LEVELS.get(level, {})
            gift_amount_usdt = level_info.get("amount", 0)
            total_gifts_usdt += table.gifts_received * gift_amount_usdt
        
        text = f"🎁 <b>Ваши подарки: {total_gifts_usdt:,} USDT</b>\n\nВыберите доску:"
        
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )


# ===========================================
# ПРОСМОТР ДОСКИ
# ===========================================

@router.callback_query(F.data.startswith("view_board:"))
async def cb_view_board(callback: CallbackQuery):
    """Показать детальную информацию о доске."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    table_id = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        user_service = UserService(session)
        
        table = await table_service.get_by_id(table_id)
        if not table:
            await callback.answer("❌ Доска не найдена", show_alert=True)
            return
        
        # Получаем позицию пользователя
        position = await table_service.get_user_position(table, tid)
        position_name = get_position_name_ru(position) if position else "Наблюдатель"
        
        # Получаем информацию об уровне
        level_info = LEVELS.get(table.level, {})
        level_name = level_info.get('name', f'L{table.level}')
        amount = level_info.get('amount', 0)
        
        # Подсчёт дарителей на доске
        donors_count = sum([
            1 for d in [table.dl1, table.dl2, table.dl3, table.dl4,
                       table.dr5, table.dr6, table.dr7, table.dr8] if d
        ])
        
        # Подсчёт партнёров пользователя на доске
        user = await user_service.get_by_tid(tid)
        referrals = await user_service.get_referrals(tid) if user else []
        referral_tids = [r.tid for r in referrals]
        
        all_on_board = [
            table.rec, table.crl, table.crr,
            table.stl1, table.stl2, table.str3, table.str4,
            table.dl1, table.dl2, table.dl3, table.dl4,
            table.dr5, table.dr6, table.dr7, table.dr8
        ]
        partners_on_board = len([t for t in all_on_board if t in referral_tids])
        
        # Квалификация (упрощённо — есть ли рефералы)
        qualification = "✅" if user and user.refscount > 0 else "❌"
        
        # Формируем сообщение как на референсе
        text = (
            f"➕ Доска - 💚 {level_name}\n"
            f"🪻 ID доски: {table.id}\n"
            f"👥 Дарителей на доске: {donors_count}\n"
            f"🎁 Подтверждено: {table.gifts_received} из 8\n"
            f"📍 Место: {position_name}\n"
            f"🔑 Квалификация: {qualification}\n"
            f"👫 Партнёров на доске: {partners_on_board}\n"
            f"🔄 Пройдено досок: —"  # TODO: добавить счётчик
        )
        
        kb = get_board_detail_kb(table.id, position)
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    
    await callback.answer()


# ===========================================
# ГЕНЕРАЦИЯ КАРТИНКИ ДОСКИ
# ===========================================

@router.callback_query(F.data.startswith("show_board_image:"))
async def cb_show_board_image(callback: CallbackQuery):
    """Показать доску картинкой с логинами."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    table_id = int(callback.data.split(":")[1])
    
    await callback.answer("🖼 Генерирую картинку...")
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        user_service = UserService(session)
        
        table = await table_service.get_by_id(table_id)
        if not table:
            await callback.answer("❌ Доска не найдена", show_alert=True)
            return
        
        # Получаем имена всех участников
        user_map = await get_user_map(session, table)
        
        # Получаем рефералов текущего пользователя
        referrals = await user_service.get_referrals(tid)
        referral_tids = [r.tid for r in referrals]
        
        # Генерируем изображение
        image_service = get_board_image_service()
        image_bytes = await image_service.generate_board_image(
            table=table,
            user_map=user_map,
            current_user_tid=tid,
            referral_tids=referral_tids,
        )
        
        # Отправляем как фото
        level_info = LEVELS.get(table.level, {})
        caption = (
            f"➕ Обозначения на доске:\n"
            f"🔴 Красный цвет - ваш логин\n"
            f"🔵 Синий цвет - ваша 1-я линия"
        )
        
        photo = BufferedInputFile(image_bytes.read(), filename=f"board_{table_id}.png")
        
        await callback.message.answer_photo(
            photo=photo,
            caption=caption,
            reply_markup=get_back_kb(table_id),
            parse_mode="HTML"
        )


# ===========================================
# ДАННЫЕ ПОЛУЧАТЕЛЯ
# ===========================================

@router.callback_query(F.data.startswith("receiver_info:"))
async def cb_receiver_info(callback: CallbackQuery):
    """Показать данные получателя доски."""
    if not callback.from_user or not callback.data:
        return
    
    table_id = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        user_service = UserService(session)
        
        table = await table_service.get_by_id(table_id)
        if not table or not table.rec:
            await callback.answer("❌ Получатель не найден", show_alert=True)
            return
        
        receiver = await user_service.get_by_tid(table.rec)
        if not receiver:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        level_info = LEVELS.get(table.level, {})
        
        text = (
            f"🎁 <b>Данные получателя</b>\n\n"
            f"👤 Имя: {receiver.display_name}\n"
            f"🆔 Username: @{receiver.username or '—'}\n"
            f"💼 Кошелёк: <code>{receiver.wallet_address or 'Не указан'}</code>\n\n"
            f"💰 Сумма подарка: <b>{level_info.get('amount', 0)} USDT</b>"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_back_kb(table_id),
            parse_mode="HTML"
        )
    
    await callback.answer()


# ===========================================
# ПОКАЗАТЬ КОМАНДУ ДОСКИ
# ===========================================

@router.callback_query(F.data.startswith("show_team:"))
async def cb_show_team(callback: CallbackQuery):
    """Показать всех участников доски."""
    if not callback.from_user or not callback.data:
        return
    
    table_id = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        table = await table_service.get_by_id(table_id)
        if not table:
            await callback.answer("❌ Доска не найдена", show_alert=True)
            return
        
        user_map = await get_user_map(session, table)
        
        def format_slot(slot_name: str, tid: Optional[int], is_paid: bool = False) -> str:
            emoji = get_position_emoji(slot_name)
            pos_name = get_position_name_ru(slot_name)
            if tid:
                name = user_map.get(tid, f"ID:{tid}")
                status = "✅" if is_paid else "⏳" if slot_name.startswith('d') else ""
                return f"{emoji} {pos_name}: {name} {status}"
            else:
                return f"{emoji} {pos_name}: <i>Свободно</i>"
        
        lines = [
            f"👥 <b>Команда доски #{table_id}</b>\n",
            format_slot('rec', table.rec),
            "",
            "<b>Создатели:</b>",
            format_slot('crl', table.crl),
            format_slot('crr', table.crr),
            "",
            "<b>Строители:</b>",
            format_slot('stl1', table.stl1),
            format_slot('stl2', table.stl2),
            format_slot('str3', table.str3),
            format_slot('str4', table.str4),
            "",
            "<b>Дарители:</b>",
            format_slot('dl1', table.dl1, table.dl1_pay),
            format_slot('dl2', table.dl2, table.dl2_pay),
            format_slot('dl3', table.dl3, table.dl3_pay),
            format_slot('dl4', table.dl4, table.dl4_pay),
            format_slot('dr5', table.dr5, table.dr5_pay),
            format_slot('dr6', table.dr6, table.dr6_pay),
            format_slot('dr7', table.dr7, table.dr7_pay),
            format_slot('dr8', table.dr8, table.dr8_pay),
        ]
        
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=get_back_kb(table_id),
            parse_mode="HTML"
        )
    
    await callback.answer()


# ===========================================
# ПОКАЗАТЬ ДАРИТЕЛЕЙ
# ===========================================

@router.callback_query(F.data.startswith("show_donors:"))
async def cb_show_donors(callback: CallbackQuery):
    """Показать только дарителей с их статусами."""
    if not callback.from_user or not callback.data:
        return
    
    table_id = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        table = await table_service.get_by_id(table_id)
        if not table:
            await callback.answer("❌ Доска не найдена", show_alert=True)
            return
        
        user_map = await get_user_map(session, table)
        
        donors = [
            ('dl1', table.dl1, table.dl1_pay, 'Левая'),
            ('dl2', table.dl2, table.dl2_pay, 'Левая'),
            ('dl3', table.dl3, table.dl3_pay, 'Левая'),
            ('dl4', table.dl4, table.dl4_pay, 'Левая'),
            ('dr5', table.dr5, table.dr5_pay, 'Правая'),
            ('dr6', table.dr6, table.dr6_pay, 'Правая'),
            ('dr7', table.dr7, table.dr7_pay, 'Правая'),
            ('dr8', table.dr8, table.dr8_pay, 'Правая'),
        ]
        
        lines = [f"👤 <b>Дарители доски #{table_id}</b>\n"]
        
        # Левая сторона
        lines.append("<b>◀️ Левая сторона:</b>")
        for slot, tid, is_paid, side in donors[:4]:
            if tid:
                name = user_map.get(tid, f"ID:{tid}")
                status = "✅ Оплачено" if is_paid else "⏳ Ожидание"
                lines.append(f"  {name} — {status}")
            else:
                lines.append(f"  <i>Свободно</i>")
        
        # Правая сторона
        lines.append("\n<b>▶️ Правая сторона:</b>")
        for slot, tid, is_paid, side in donors[4:]:
            if tid:
                name = user_map.get(tid, f"ID:{tid}")
                status = "✅ Оплачено" if is_paid else "⏳ Ожидание"
                lines.append(f"  {name} — {status}")
            else:
                lines.append(f"  <i>Свободно</i>")
        
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=get_back_kb(table_id),
            parse_mode="HTML"
        )
    
    await callback.answer()


# ===========================================
# ВЫБОР УРОВНЯ И ВХОД
# ===========================================

@router.callback_query(F.data == "back_to_levels")
async def cb_back_to_levels(callback: CallbackQuery):
    """Вернуться к выбору уровня."""
    await callback.message.edit_text(
        "🚀 <b>Выберите уровень доски:</b>",
        reply_markup=get_levels_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("level_info:"))
async def cb_level_info(callback: CallbackQuery):
    """Информация о недоступном уровне."""
    if not callback.from_user or not callback.data:
        return
    
    level = int(callback.data.split(":")[1])
    level_info = LEVELS.get(level, {})
    level_name = level_info.get("name", f"Уровень {level}")
    amount = level_info.get("amount", 0)
    
    # Маппинг русских названий
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
    level_name_ru = level_names_ru.get(level, level_name)
    
    text = (
        f"❌ <b>{level_name_ru} доска недоступна</b>\n\n"
        f"Номинал подарка: <b>{amount} USDT</b>\n\n"
        f"Эта доска ещё не активирована.\n"
        f"Активируйте предыдущие уровни, чтобы получить доступ."
    )
    
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("select_level:"))
async def cb_select_level(callback: CallbackQuery):
    """Выбор уровня — показать инфо или войти."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    level = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        # Проверяем есть ли уже доска на этом уровне
        user_tables = await table_service.get_user_tables(tid)
        existing = next((t for t in user_tables if t.level == level), None)
        
        if existing:
            # Показываем существующую доску
            callback.data = f"view_board:{existing.id}"
            await cb_view_board(callback)
        else:
            # Предлагаем войти
            level_info = LEVELS.get(level, {})
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🚀 Активировать доску",
                    callback_data=f"join_level:{level}"
                )],
                [InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="back_to_levels"
                )]
            ])
            
            text = (
                f"🌟 <b>Уровень {level}: {level_info.get('name', '')}</b>\n"
                f"🎁 Сумма подарка: <b>{level_info.get('amount', 0)} USDT</b>\n\n"
                f"Вы пока не участвуете на этом уровне.\n"
                f"Хотите занять место?"
            )
            
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    
    await callback.answer()


@router.callback_query(F.data.startswith("join_level:"))
async def cb_join_level(callback: CallbackQuery):
    """Войти на доску уровня."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    level = int(callback.data.split(":")[1])
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        
        # Ищем доску
        table, reason = await table_service.find_table_for_user(tid, level)
        
        if not table:
            await callback.answer(
                f"❌ Нет доступных досок. Код: {reason}",
                show_alert=True
            )
            return
        
        # Пробуем войти
        success, join_result, slot = await table_service.join_table(table.id, tid)
        
        if success:
            await callback.answer("✅ Вы заняли место!", show_alert=True)
            # Показываем доску
            callback.data = f"view_board:{table.id}"
            await cb_view_board(callback)
        else:
            error_map = {
                JoinResult.USER_ALREADY_ON_LEVEL.value: "Вы уже на этом уровне!",
                JoinResult.USER_BLOCKED.value: "Вы заблокированы!",
                JoinResult.NO_SLOTS.value: "Места закончились!",
                JoinResult.TABLE_CLOSED.value: "Доска закрыта!",
            }
            error_text = error_map.get(join_result, f"Ошибка: {join_result}")
            await callback.answer(f"❌ {error_text}", show_alert=True)
