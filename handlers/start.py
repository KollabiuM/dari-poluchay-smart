"""
Обработчики команд пользователя.
/start, /myref, /myrefs, /mymentor, /mystatus, кнопка "Я тут".
"""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

from database import AsyncSessionLocal
from services.user_service import UserService
from keyboards.user_keyboards import (
    get_main_menu_kb,
    get_heartbeat_kb,
    get_wallet_connect_kb,
)
from texts.messages import (
    get_welcome_message,
    get_welcome_back_message,
    get_blocked_message,
    get_dormant_warning_message,
)

router = Router(name="start")
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    """
    Обработчик команды /start.
    Поддерживает deep-link для рефералов: /start dp_123456789
    """
    if not message.from_user:
        return
    
    tid = message.from_user.id
    username = message.from_user.username
    fullname = message.from_user.full_name
    
    # Извлекаем реферальный код из deep link (CommandObject - идея из Gemini)
    referrer_tid: Optional[int] = None
    referrer_name: Optional[str] = None
    
    if command.args:
        reflink_code = command.args
        
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            referrer = await user_service.get_by_reflink(reflink_code)
            
            if referrer and referrer.tid != tid:
                referrer_tid = referrer.tid
                referrer_name = referrer.display_name
                logger.info(f"User {tid} пришёл по ссылке от {referrer_tid}")
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        
        # Регистрируем или получаем пользователя
        user, is_new = await user_service.register_or_get(
            tid=tid,
            username=username,
            fullname=fullname,
            referrer_tid=referrer_tid,
        )
        
        # Проверяем блокировку
        if user.isblocked:
            await message.answer(get_blocked_message(), parse_mode="HTML")
            return
        
        if user.is_banned:
            await message.answer(
                f"⛔ Вы заблокированы ещё на {user.ban_remaining_hours} часов.\n\n"
                f"💰 Снять блокировку: оплатите 150 USDT",
                parse_mode="HTML"
            )
            return
        
        if is_new:
            logger.info(f"Новый пользователь: {tid} ({username})")
            
            # Получаем имя наставника для сообщения
            if not referrer_name and referrer_tid:
                ref = await user_service.get_by_tid(referrer_tid)
                if ref:
                    referrer_name = ref.display_name
            
            welcome_text = get_welcome_message(
                name=fullname or username or "друг",
                referrer_name=referrer_name,
                reflink=user.referral_link,
            )
            
            # TODO: Показать Disclaimer для подписания
            
        else:
            logger.info(f"Возврат пользователя: {tid}")
            
            # Получаем наставника
            referrer = await user_service.get_referrer(user)
            referrer_name = referrer.display_name if referrer else None
            
            welcome_text = get_welcome_back_message(
                name=fullname or username or "друг",
                referrer_name=referrer_name,
                reflink=user.referral_link,
                refs_count=user.refscount,
                is_globally_active=user.is_globally_active,
                is_heartbeat_active=user.is_heartbeat_active,
                global_days=user.global_activity_remaining_days,
                heartbeat_hours=user.heartbeat_remaining_hours,
            )
    
    await message.answer(
        welcome_text, 
        parse_mode="HTML",
        reply_markup=get_main_menu_kb(),
    )


@router.message(Command("myref"))
async def cmd_myref(message: Message) -> None:
    """Показать реферальную ссылку пользователя."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        text = (
            f"🔗 <b>Ваша реферальная ссылка:</b>\n\n"
            f"<code>{user.referral_link}</code>\n\n"
            f"👥 Приглашено партнёров: <b>{user.refscount}</b>\n\n"
            f"💡 Отправьте эту ссылку друзьям!\n"
            f"За каждого партнёра вы получаете 30 дней глобальной активности."
        )
        
        await message.answer(text, parse_mode="HTML")


@router.message(Command("myrefs"))
async def cmd_myrefs(message: Message) -> None:
    """Показать список рефералов пользователя."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        referrals = await user_service.get_referrals(tid, limit=20)
        
        if not referrals:
            text = (
                f"👥 <b>Ваши партнёры</b>\n\n"
                f"У вас пока нет приглашённых партнёров.\n\n"
                f"🔗 Ваша ссылка:\n"
                f"<code>{user.referral_link}</code>"
            )
        else:
            refs_list = "\n".join(
                f"  {i+1}. {ref.display_name} {'✅' if not ref.is_dormant else '😴'}"
                for i, ref in enumerate(referrals)
            )
            
            text = (
                f"👥 <b>Ваши партнёры ({user.refscount})</b>\n\n"
                f"{refs_list}\n\n"
                f"✅ — активен, 😴 — спящий\n\n"
                f"🔗 Ваша ссылка:\n"
                f"<code>{user.referral_link}</code>"
            )
        
        await message.answer(text, parse_mode="HTML")


@router.message(Command("mymentor"))
async def cmd_mymentor(message: Message) -> None:
    """Показать информацию о наставнике."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        referrer = await user_service.get_referrer(user)
        
        if not referrer:
            text = (
                f"👤 <b>Ваш наставник</b>\n\n"
                f"У вас нет наставника.\n"
                f"Вы зарегистрировались самостоятельно."
            )
        else:
            status = "✅ Активен" if not referrer.is_dormant else "😴 Спящий"
            text = (
                f"👤 <b>Ваш наставник</b>\n\n"
                f"Имя: {referrer.display_name}\n"
                f"Статус: {status}\n"
                f"ID: <code>{referrer.tid}</code>"
            )
        
        await message.answer(text, parse_mode="HTML")


@router.message(Command("mystatus"))
async def cmd_mystatus(message: Message) -> None:
    """Показать полный статус пользователя."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        # Статус глобальной активности
        if user.is_globally_active:
            global_status = f"✅ Активна ({user.global_activity_remaining_days} дней)"
        else:
            global_status = "❌ Истекла — пригласите партнёра!"
        
        # Статус текущей активности
        if user.is_heartbeat_active:
            heartbeat_status = f"✅ Активна ({user.heartbeat_remaining_hours} часов)"
        else:
            heartbeat_status = "❌ Истекла — нажмите 'Я тут'!"
        
        # Статус блокировки
        if user.isblocked:
            ban_status = "⛔ Постоянная блокировка (Blacklist)"
        elif user.is_banned:
            ban_status = f"⛔ Заблокирован ({user.ban_remaining_hours} часов)"
        else:
            ban_status = "✅ Нет блокировок"
        
        # Кошелёк
        if user.wallet_address:
            wallet_short = f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}"
            wallet_status = f"✅ {wallet_short}"
        else:
            wallet_status = "❌ Не подключён"
        
        # Общий статус
        if user.can_participate:
            overall = "🟢 Можете участвовать"
        else:
            overall = "🔴 Участие ограничено"
        
        text = (
            f"📊 <b>Ваш статус</b>\n\n"
            f"<b>Общий:</b> {overall}\n\n"
            f"<b>Глобальная активность (30д):</b>\n{global_status}\n\n"
            f"<b>Текущая активность (48ч):</b>\n{heartbeat_status}\n\n"
            f"<b>Блокировки:</b>\n{ban_status}\n"
            f"Нарушений: {user.votes}\n\n"
            f"<b>Кошелёк:</b> {wallet_status}\n\n"
            f"<b>Партнёров:</b> {user.refscount}"
        )
        
        await message.answer(
            text, 
            parse_mode="HTML",
            reply_markup=get_heartbeat_kb() if not user.is_heartbeat_active else None,
        )


@router.message(Command("heartbeat"))
@router.message(F.text == "✅ Я тут!")
async def cmd_heartbeat(message: Message) -> None:
    """Кнопка 'Я тут' — продление текущей активности на 48 часов."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        # Проверяем глобальную активность (нужна для нажатия)
        if not user.is_globally_active:
            await message.answer(
                "⚠️ <b>Глобальная активность истекла!</b>\n\n"
                "Чтобы нажать 'Я тут', сначала пригласите партнёра.\n\n"
                f"🔗 Ваша ссылка:\n<code>{user.referral_link}</code>",
                parse_mode="HTML"
            )
            return
        
        # Проверяем блокировку
        if user.is_banned:
            await message.answer(
                f"⛔ Вы заблокированы ещё на {user.ban_remaining_hours} часов.\n"
                "Нельзя нажимать 'Я тут' во время блокировки.",
                parse_mode="HTML"
            )
            return
        
        success = await user_service.press_heartbeat(tid)
        
        if success:
            # Получаем обновлённые данные
            user = await user_service.get_by_tid(tid)
            
            text = (
                f"✅ <b>Активность продлена на 48 часов!</b>\n\n"
                f"⏰ Следующее нажатие до: {user.heartbeat_remaining_hours} часов\n\n"
                f"🔗 Ваша реферальная ссылка:\n"
                f"<code>{user.referral_link}</code>\n\n"
            )
            
            # Напоминание о глобальной активности
            if user.global_activity_remaining_days <= 5:
                text += (
                    f"⚠️ <b>Внимание!</b> Глобальная активность истекает "
                    f"через {user.global_activity_remaining_days} дней.\n"
                    f"Пригласите друга, чтобы продлить!"
                )
            
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer("❌ Не удалось продлить активность.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Справка по командам."""
    text = (
        "📋 <b>Доступные команды:</b>\n\n"
        "/start — Регистрация / Главное меню\n"
        "/myref — Ваша реферальная ссылка\n"
        "/myrefs — Список ваших партнёров\n"
        "/mymentor — Информация о наставнике\n"
        "/mystatus — Полный статус аккаунта\n"
        "/heartbeat — Продлить активность (Я тут)\n"
        "/help — Эта справка\n\n"
        "💡 <b>Как работает система:</b>\n"
        "1. Пригласите друга — получите 30 дней активности\n"
        "2. Нажимайте 'Я тут' каждые 48 часов\n"
        "3. Подключите кошелёк и активируйте доску"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "🫶 О нас")
async def cmd_about(message: Message) -> None:
    """Информация о проекте."""
    text = (
        "🫶 <b>О проекте Дари Получай Smart</b>\n\n"
        "Мы — платформа взаимных подарков на блокчейне TON.\n\n"
        "<b>Наша миссия:</b>\n"
        "Создать честную и прозрачную систему взаимопомощи, "
        "где каждый участник может получить поддержку сообщества.\n\n"
        "<b>Как это работает:</b>\n"
        "• 15-местные матрицы с 13 уровнями\n"
        "• Автоматические переводы через смарт-контракты\n"
        "• Компрессия по цепочке наставников\n"
        "• Прозрачность всех операций в блокчейне\n\n"
        "<b>Преимущества:</b>\n"
        "✅ Безопасность — смарт-контракты\n"
        "✅ Прозрачность — все в блокчейне\n"
        "✅ Справедливость — компрессия активных\n"
        "✅ Автоматизация — без ручного управления\n\n"
        "🚀 Присоединяйтесь к нашему сообществу!"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📄 Инструкции")
async def cmd_instructions(message: Message) -> None:
    """Инструкции по использованию бота."""
    text = (
        "📄 <b>Инструкции по использованию</b>\n\n"
        "<b>1. Регистрация</b>\n"
        "Отправьте /start для регистрации в системе.\n"
        "При регистрации по реферальной ссылке вы автоматически "
        "привязываетесь к наставнику.\n\n"
        "<b>2. Активация</b>\n"
        "• Пригласите друга — получите 30 дней глобальной активности\n"
        "• Нажимайте 'Я тут' каждые 48 часов\n"
        "• Подключите TON кошелёк для участия в досках\n\n"
        "<b>3. Работа с досками</b>\n"
        "• Выберите уровень доски (Start — 10 USDT)\n"
        "• Система найдёт подходящую доску по компрессии\n"
        "• Займите место дарителя\n"
        "• Отправьте подарок получателю в течение 72 часов\n"
        "• Получатель подтверждает получение\n\n"
        "<b>4. Становление получателем</b>\n"
        "Когда доска заполнится и все дарители оплатят, "
        "вы можете стать получателем на новой доске.\n\n"
        "<b>5. Разделение досок</b>\n"
        "Когда одна сторона доски (4 дарителя) полностью оплачена, "
        "доска может разделиться, создав новую доску.\n\n"
        "<b>6. Уровни</b>\n"
        "Всего 13 уровней: Start ($10) → Titan ($40,960)\n"
        "Каждый уровень удваивает сумму подарка.\n\n"
        "💡 <b>Важно:</b>\n"
        "• Соблюдайте сроки оплаты (72 часа)\n"
        "• Поддерживайте активность (нажимайте 'Я тут')\n"
        "• Приглашайте активных партнёров\n\n"
        "❓ Вопросы? Используйте /help"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "🔰 Мой статус")
async def cmd_my_status_button(message: Message) -> None:
    """Обработчик кнопки 'Мой статус'."""
    # Используем тот же обработчик что и для /mystatus
    await cmd_mystatus(message)


@router.message(F.text == "👋 Приглашение")
async def cmd_invite(message: Message) -> None:
    """Показать реферальную ссылку и информацию о приглашении."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        # Получаем наставника
        referrer = await user_service.get_referrer(user)
        referrer_name = referrer.display_name if referrer else None
        
        # Статистика рефералов
        referrals = await user_service.get_referrals(tid, limit=10)
        active_count = sum(1 for ref in referrals if not ref.is_dormant)
        dormant_count = len(referrals) - active_count
        
        text = (
            f"👋 <b>Приглашение партнёров</b>\n\n"
            f"🔗 <b>Ваша реферальная ссылка:</b>\n"
            f"<code>{user.referral_link}</code>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"• Всего приглашено: <b>{user.refscount}</b>\n"
            f"• Активных: <b>{active_count}</b> ✅\n"
            f"• Спящих: <b>{dormant_count}</b> 😴\n\n"
        )
        
        if referrer_name:
            text += f"👤 Ваш наставник: <b>{referrer_name}</b>\n\n"
        
        text += (
            f"💡 <b>Как приглашать:</b>\n"
            f"1. Отправьте ссылку другу\n"
            f"2. Он переходит по ссылке и регистрируется\n"
            f"3. Вы получаете +30 дней глобальной активности\n"
            f"4. Ваш партнёр становится активным участником\n\n"
            f"🎁 <b>Бонус:</b>\n"
            f"За каждого активного партнёра вы получаете "
            f"продление глобальной активности на 30 дней!"
        )
        
        await message.answer(text, parse_mode="HTML")


@router.message(F.text == "🛠️ Инструменты")
async def cmd_tools(message: Message) -> None:
    """Меню инструментов."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        text = (
            f"🛠️ <b>Инструменты</b>\n\n"
            f"<b>Быстрые действия:</b>\n"
            f"• /myref — Реферальная ссылка\n"
            f"• /myrefs — Список партнёров\n"
            f"• /mymentor — Информация о наставнике\n"
            f"• /mystatus — Полный статус\n"
            f"• /boards — Мои доски\n"
            f"• /levels — Все уровни\n"
            f"• /help — Справка\n\n"
        )
        
        if user.wallet_address:
            wallet_short = f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}"
            text += f"💼 <b>Кошелёк:</b> <code>{wallet_short}</code>\n\n"
        else:
            text += (
                f"💼 <b>Кошелёк:</b> Не подключён\n"
                f"Нажмите кнопку '💼 Кошелёк' для подключения\n\n"
            )
        
        text += (
            f"📊 <b>Ваша статистика:</b>\n"
            f"• Партнёров: {user.refscount}\n"
            f"• Глобальная активность: "
            f"{'✅' if user.is_globally_active else '❌'}\n"
            f"• Текущая активность: "
            f"{'✅' if user.is_heartbeat_active else '❌'}\n"
        )
        
        await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💼 Кошелёк")
async def cmd_wallet(message: Message) -> None:
    """Управление кошельком."""
    if not message.from_user:
        return
    
    tid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user_service = UserService(session)
        user = await user_service.get_by_tid(tid)
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
            return
        
        if user.wallet_address:
            wallet_short = f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}"
            text = (
                f"💼 <b>Ваш кошелёк подключён</b>\n\n"
                f"Адрес: <code>{user.wallet_address}</code>\n"
                f"Короткий: <code>{wallet_short}</code>\n\n"
                f"✅ Вы можете:\n"
                f"• Получать подарки на этот адрес\n"
                f"• Отправлять подарки другим участникам\n"
                f"• Участвовать в досках\n\n"
                f"💡 Для смены кошелька используйте команду /set_wallet"
            )
        else:
            text = (
                f"💼 <b>Подключение кошелька</b>\n\n"
                f"Для участия в системе вам нужно подключить TON кошелёк.\n\n"
                f"<b>Как подключить:</b>\n"
                f"1. Установите @wallet бота\n"
                f"2. Создайте или откройте кошелёк\n"
                f"3. Скопируйте адрес кошелька\n"
                f"4. Отправьте команду: /set_wallet &lt;адрес&gt;\n\n"
                f"<b>Пример:</b>\n"
                f"<code>/set_wallet EQD...abc123</code>\n\n"
                f"⚠️ <b>Внимание:</b>\n"
                f"Используйте только адреса TON кошельков.\n"
                f"После подключения вы сможете участвовать в досках."
            )
        
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_wallet_connect_kb() if not user.wallet_address else None,
        )
