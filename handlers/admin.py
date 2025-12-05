"""
Административные команды.
Создание досок, управление пользователями.
"""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import AsyncSessionLocal
from services.table_service import TableService
from services.user_service import UserService
from models.table import LEVELS, Table

router = Router(name="admin")
logger = logging.getLogger(__name__)

# Суперадмины (хардкод) — могут назначать других админов
SUPER_ADMIN_IDS = [
    288353811,  # Aleksandr
]

async def is_admin(tid: int) -> bool:
    """
    Проверка прав администратора.
    1. Сначала проверяем хардкод (суперадмины)
    2. Затем проверяем БД (user.isadmin)
    """
    # Суперадмины всегда имеют доступ
    if tid in SUPER_ADMIN_IDS:
        return True
    
    # Проверяем флаг в БД
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        return user is not None and user.isadmin


async def is_super_admin(tid: int) -> bool:
    """Проверка суперадмина (только хардкод)."""
    return tid in SUPER_ADMIN_IDS


def get_create_level_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора уровня для создания доски."""
    buttons = []
    
    row = []
    for level in range(1, 14):
        info = LEVELS[level]
        row.append(InlineKeyboardButton(
            text=f"{info['name']} ({info['amount']}$)",
            callback_data=f"admin_create:{level}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ===========================================
# СОЗДАНИЕ ДОСОК
# ===========================================

@router.message(Command("create"))
@router.message(Command("create_table"))
@router.message(Command("create_genesis"))
async def cmd_create_table(message: Message, command: CommandObject) -> None:
    """
    Создать новую доску (Genesis).
    
    /create — меню выбора уровня
    /create 1 — создать доску Start
    """
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    if not await is_admin(tid):
        await message.answer("⛔ Только для администраторов")
        return
    
    if command.args and command.args.isdigit():
        level = int(command.args)
        
        if level < 1 or level > 13:
            await message.answer("❌ Уровень должен быть от 1 до 13")
            return
        
        await create_table_for_user(message, tid, level)
        return
    
    await message.answer(
        "🛠 <b>Создание Genesis-доски</b>\n\n"
        "Вы станете Получателем (REC).\n"
        "Выберите уровень:",
        parse_mode="HTML",
        reply_markup=get_create_level_kb(),
    )


@router.callback_query(F.data.startswith("admin_create:"))
async def callback_admin_create(callback: CallbackQuery) -> None:
    """Создание доски через callback."""
    if not callback.from_user or not callback.data:
        return
    
    tid = callback.from_user.id
    
    if not await is_admin(tid):
        await callback.answer("⛔ Только для администраторов", show_alert=True)
        return
    
    level = int(callback.data.split(":")[1])
    await create_table_for_user(callback.message, tid, level, callback)


async def create_table_for_user(
    message: Message,
    creator_tid: int,
    level: int,
    callback: Optional[CallbackQuery] = None,
) -> None:
    """Создать доску и уведомить."""
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        user_service = UserService(session)
        
        user = await user_service.get_by_tid(creator_tid)
        if not user:
            text = "❌ Сначала зарегистрируйтесь: /start"
            if callback:
                await callback.answer(text, show_alert=True)
            else:
                await message.answer(text)
            return
        
        # Проверяем нет ли уже доски
        existing = await table_service.find_receiver_table(creator_tid, level)
        if existing:
            text = f"⚠️ У вас уже есть доска #{existing.id} на уровне {level}"
            if callback:
                await callback.answer(text, show_alert=True)
            else:
                await message.answer(text)
            return
        
        # Создаём
        table = await table_service.create_table(
            level=level,
            creator_tid=creator_tid,
        )
        
        level_info = LEVELS[level]
        
        text = (
            f"✨ <b>Genesis Table Created!</b>\n\n"
            f"🆔 ID: <code>#{table.id}</code>\n"
            f"🎯 Уровень: <b>{level_info['name']}</b>\n"
            f"💰 Сумма подарка: <b>{level_info['amount']} USDT</b>\n"
            f"📍 Вы: <b>Получатель (REC)</b>\n\n"
            f"Теперь участники могут присоединяться!\n"
            f"📋 Посмотреть: /board {table.id}"
        )
        
        logger.info(f"Genesis доска #{table.id} L{level} создана tid={creator_tid}")
        
        if callback:
            await callback.message.edit_text(text, parse_mode="HTML")
            await callback.answer("✅ Доска создана!")
        else:
            await message.answer(text, parse_mode="HTML")


# ===========================================
# УПРАВЛЕНИЕ АДМИНАМИ
# ===========================================

@router.message(Command("set_admin"))
async def cmd_set_admin(message: Message, command: CommandObject) -> None:
    """
    Назначить пользователя админом.
    Только для суперадминов!
    
    /set_admin 123456789
    """
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    # Только суперадмины могут назначать админов
    if not await is_super_admin(tid):
        await message.answer("⛔ Только для суперадминов")
        return
    
    if not command.args:
        await message.answer(
            "📋 <b>Использование:</b>\n"
            "<code>/set_admin 123456789</code>",
            parse_mode="HTML",
        )
        return
    
    try:
        target_tid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ TID должен быть числом")
        return
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(target_tid)
        
        if not user:
            await message.answer(f"❌ Пользователь {target_tid} не найден в БД")
            return
        
        if user.isadmin:
            await message.answer(f"ℹ️ {user.display_name} уже админ")
            return
        
        user.isadmin = True
        await session.commit()
        
        logger.info(f"Пользователь {target_tid} назначен админом (by {tid})")
        
        await message.answer(
            f"✅ <b>{user.display_name}</b> теперь администратор!",
            parse_mode="HTML",
        )


@router.message(Command("remove_admin"))
async def cmd_remove_admin(message: Message, command: CommandObject) -> None:
    """
    Снять права админа.
    
    /remove_admin 123456789
    """
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    if not await is_super_admin(tid):
        await message.answer("⛔ Только для суперадминов")
        return
    
    if not command.args:
        await message.answer("📋 <b>Использование:</b>\n<code>/remove_admin 123456789</code>", parse_mode="HTML")
        return
    
    try:
        target_tid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ TID должен быть числом")
        return
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(target_tid)
        
        if not user:
            await message.answer(f"❌ Пользователь {target_tid} не найден")
            return
        
        user.isadmin = False
        await session.commit()
        
        await message.answer(f"✅ {user.display_name} больше не админ")


@router.message(Command("admins"))
async def cmd_list_admins(message: Message) -> None:
    """Показать список админов."""
    if not message.from_user:
        return
    
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Только для администраторов")
        return
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from models.user import User
        
        query = select(User).where(User.isadmin == True)
        result = await session.execute(query)
        admins = list(result.scalars().all())
        
        lines = ["👑 <b>Администраторы</b>\n"]
        lines.append("<b>Суперадмины (хардкод):</b>")
        for tid in SUPER_ADMIN_IDS:
            lines.append(f"  • <code>{tid}</code>")
        
        if not SUPER_ADMIN_IDS:
            lines.append("  <i>Не настроены</i>")
        
        lines.append("\n<b>Админы (БД):</b>")
        for admin in admins:
            lines.append(f"  • {admin.display_name} (<code>{admin.tid}</code>)")
        
        if not admins:
            lines.append("  <i>Нет</i>")
        
        await message.answer("\n".join(lines), parse_mode="HTML")


# ===========================================
# СТАТИСТИКА
# ===========================================

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Статистика системы."""
    if not message.from_user:
        return
    
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Только для администраторов")
        return
    
    async with AsyncSessionLocal() as session:
        table_service = TableService(session)
        user_service = UserService(session)
        
        # Статистика досок
        lines = ["📊 <b>Статистика системы</b>\n"]
        
        total_active = 0
        total_closed = 0
        
        for level in range(1, 14):
            stats = await table_service.get_tables_stats(level)
            
            if stats["total"] > 0:
                lines.append(
                    f"<b>L{level} {stats['level_name']}</b>: "
                    f"🟢 {stats['active']} / ✅ {stats['closed']}"
                )
                total_active += stats["active"]
                total_closed += stats["closed"]
        
        lines.append("")
        lines.append(f"<b>Всего досок:</b> 🟢 {total_active} / ✅ {total_closed}")
        
        # Статистика пользователей
        from sqlalchemy import select, func
        from models.user import User
        
        users_count = await session.execute(select(func.count(User.id)))
        total_users = users_count.scalar() or 0
        
        lines.append(f"<b>Пользователей:</b> {total_users}")
        
        if total_active == 0:
            lines.append("\n💡 Досок нет. Создайте: /create")
        
        await message.answer("\n".join(lines), parse_mode="HTML")


# ===========================================
# СПИСОК ДОСОК
# ===========================================

@router.message(Command("tables"))
async def cmd_list_tables(message: Message, command: CommandObject) -> None:
    """
    Список досок.
    
    /tables — все активные
    /tables 1 — только уровень 1
    """
    if not message.from_user:
        return
    
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Только для администраторов")
        return
    
    level_filter = None
    if command.args and command.args.isdigit():
        level_filter = int(command.args)
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, and_
        
        conditions = [Table.isactive == True]
        if level_filter:
            conditions.append(Table.level == level_filter)
        
        query = (
            select(Table)
            .where(and_(*conditions))
            .order_by(Table.level, Table.id)
            .limit(20)
        )
        result = await session.execute(query)
        tables = list(result.scalars().all())
        
        if not tables:
            await message.answer("📋 Активных досок нет.\n💡 Создайте: /create")
            return
        
        lines = ["📋 <b>Активные доски</b>\n"]
        
        for table in tables:
            level_info = LEVELS.get(table.level, {})
            level_name = level_info.get("name", f"L{table.level}")
            
            lines.append(
                f"<b>#{table.id}</b> {level_name} — "
                f"🎁 {table.gifts_received}/8 — "
                f"📍 {table.empty_slots_total} мест"
            )
        
        await message.answer("\n".join(lines), parse_mode="HTML")


# ===========================================
# УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
# ===========================================

@router.message(Command("user"))
async def cmd_user_info(message: Message, command: CommandObject) -> None:
    """
    Информация о пользователе.
    
    /user 123456789
    """
    if not message.from_user:
        return
    
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Только для администраторов")
        return
    
    if not command.args:
        await message.answer("📋 <code>/user 123456789</code>", parse_mode="HTML")
        return
    
    try:
        target_tid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ TID должен быть числом")
        return
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(target_tid)
        
        if not user:
            await message.answer(f"❌ Пользователь {target_tid} не найден")
            return
        
        # Статусы
        status = []
        if user.isadmin:
            status.append("👑 Админ")
        if user.isblocked:
            status.append("⛔ Blacklist")
        if user.is_banned:
            status.append(f"🔒 Бан ({user.ban_remaining_hours}ч)")
        if user.is_dormant:
            status.append("😴 Спящий")
        if not status:
            status.append("✅ Активен")
        
        text = (
            f"👤 <b>Пользователь</b>\n\n"
            f"TID: <code>{user.tid}</code>\n"
            f"Имя: {user.display_name}\n"
            f"Username: @{user.username or '—'}\n"
            f"Кошелёк: <code>{user.wallet_address or '—'}</code>\n\n"
            f"Статус: {', '.join(status)}\n"
            f"Нарушений: {user.votes}\n"
            f"Партнёров: {user.refscount}\n"
            f"Наставник: {user.isref or '—'}"
        )
        
        await message.answer(text, parse_mode="HTML")


@router.message(Command("ban"))
async def cmd_ban_user(message: Message, command: CommandObject) -> None:
    """Заблокировать пользователя (временно)."""
    if not message.from_user:
        return
    
    if not await is_admin(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("📋 <code>/ban 123456789</code>", parse_mode="HTML")
        return
    
    try:
        target_tid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ TID должен быть числом")
        return
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        hours = await user_service.apply_ban(target_tid)
        
        if hours:
            await message.answer(f"🔒 Пользователь {target_tid} заблокирован на {hours} часов")
        else:
            await message.answer(f"❌ Пользователь {target_tid} не найден")


@router.message(Command("unban"))
async def cmd_unban_user(message: Message, command: CommandObject) -> None:
    """Разблокировать пользователя."""
    if not message.from_user:
        return
    
    if not await is_admin(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("📋 <code>/unban 123456789</code>", parse_mode="HTML")
        return
    
    try:
        target_tid = int(command.args.strip())
    except ValueError:
        await message.answer("❌ TID должен быть числом")
        return
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        success = await user_service.pay_indulgence(target_tid)
        
        if success:
            await message.answer(f"✅ Пользователь {target_tid} разблокирован")
        else:
            await message.answer(f"❌ Не удалось разблокировать")


# ===========================================
# СПРАВКА
# ===========================================

@router.message(Command("admin"))
async def cmd_admin_help(message: Message) -> None:
    """Справка по админ-командам."""
    if not message.from_user:
        return
    
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Только для администраторов")
        return
    
    text = """🛠 <b>Админ-команды</b>

<b>Доски:</b>
/create — создать Genesis-доску
/tables — список активных досок
/stats — статистика системы

<b>Пользователи:</b>
/user &lt;tid&gt; — информация
/ban &lt;tid&gt; — заблокировать
/unban &lt;tid&gt; — разблокировать

<b>Админы:</b>
/admins — список админов
/set_admin &lt;tid&gt; — назначить админа
/remove_admin &lt;tid&gt; — снять права

💡 Ваш TID: <code>{tid}</code>
🔑 Суперадмин: {is_super}"""
    
    is_super = "✅ Да" if message.from_user.id in SUPER_ADMIN_IDS else "❌ Нет"
    
    await message.answer(
        text.format(tid=message.from_user.id, is_super=is_super),
        parse_mode="HTML",
    )
