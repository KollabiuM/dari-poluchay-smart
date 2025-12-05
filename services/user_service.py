"""
Сервис для работы с пользователями.
Регистрация, активность, блокировки, реферальная система.
"""
import time
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.user import (
    User,
    GLOBAL_ACTIVITY_DURATION,
    HEARTBEAT_DURATION,
    BAN_DURATION_FIRST,
    BAN_DURATION_SECOND,
    BAN_DURATION_THIRD,
)
from utils.send_message_utils import alert


class UserService:
    """Сервис для работы с пользователями."""

    def __init__(self, session: AsyncSession):
        """
        Инициализация сервиса.
        
        Args:
            session: Асинхронная сессия SQLAlchemy
        """
        self.session = session

    # === Базовые методы ===

    async def get_by_tid(self, tid: int) -> Optional[User]:
        """
        Получить пользователя по Telegram ID.
        
        Args:
            tid: Telegram ID пользователя
            
        Returns:
            User или None если не найден
        """
        query = select(User).where(User.tid == tid)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_reflink(self, reflink: str) -> Optional[User]:
        """
        Получить пользователя по реферальной ссылке.
        
        Args:
            reflink: Реферальный код пользователя
            
        Returns:
            User или None если не найден
        """
        query = select(User).where(User.reflink == reflink)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_user(
        self,
        tid: int,
        username: Optional[str] = None,
        fullname: Optional[str] = None,
        referrer_tid: Optional[int] = None,
    ) -> User:
        """
        Создать нового пользователя.
        
        Args:
            tid: Telegram ID
            username: Username в Telegram
            fullname: Полное имя
            referrer_tid: Telegram ID наставника (реферера)
            
        Returns:
            Созданный User
        """
        now = int(time.time())
        reflink = self._generate_reflink(tid)
        
        user = User(
            tid=tid,
            username=username,
            fullname=fullname,
            isref=referrer_tid,
            reflink=reflink,
            regtime=now,
            isactive=True,
            isadmin=False,
            isblocked=False,
            refscount=0,
            votes=0,
            # При регистрации даём 48ч на нажатие "Я тут"
            heartbeat_until=now + HEARTBEAT_DURATION,
            # Глобальная активность появится когда пригласит реферала
            global_activity_until=None,
        )
        
        self.session.add(user)
        try:
            await self.session.commit()
            await self.session.refresh(user)
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при создании пользователя tid={tid}: {e}")
            raise e
        
        return user

    async def register_or_get(
        self,
        tid: int,
        username: Optional[str] = None,
        fullname: Optional[str] = None,
        referrer_tid: Optional[int] = None,
    ) -> tuple[User, bool]:
        """
        Зарегистрировать нового пользователя или получить существующего.
        
        Args:
            tid: Telegram ID
            username: Username в Telegram
            fullname: Полное имя
            referrer_tid: Telegram ID наставника
            
        Returns:
            Tuple[User, is_new]: Пользователь и флаг "новый ли он"
        """
        existing_user = await self.get_by_tid(tid)
        
        if existing_user:
            # Обновляем данные если изменились
            await self._update_user_data(existing_user, username, fullname)
            return existing_user, False
        
        # Валидация реферала (нельзя быть своим рефералом)
        valid_referrer_tid = None
        if referrer_tid and referrer_tid != tid:
            referrer = await self.get_by_tid(referrer_tid)
            if referrer:
                valid_referrer_tid = referrer_tid
        
        # Создаём нового пользователя
        new_user = await self.create_user(
            tid=tid,
            username=username,
            fullname=fullname,
            referrer_tid=valid_referrer_tid,
        )
        
        # Обновляем наставника: +1 реферал, продление глобальной активности
        if valid_referrer_tid:
            await self._on_referral_registered(valid_referrer_tid)
        
        return new_user, True

    async def _update_user_data(
        self,
        user: User,
        username: Optional[str],
        fullname: Optional[str],
    ) -> None:
        """Обновить данные пользователя если они изменились."""
        needs_update = False
        
        if username and user.username != username:
            user.username = username
            needs_update = True
            
        if fullname and user.fullname != fullname:
            user.fullname = fullname
            needs_update = True
            
        if needs_update:
            try:
                await self.session.commit()
            except IntegrityError as e:
                await self.session.rollback()
                await alert(f"Ошибка при обновлении пользователя tid={user.tid}: {e}")
                raise e

    async def _on_referral_registered(self, referrer_tid: int) -> None:
        """
        Действия при регистрации нового реферала.
        - Увеличить счётчик рефералов
        - Продлить глобальную активность на 30 дней
        """
        now = int(time.time())
        new_global_until = now + GLOBAL_ACTIVITY_DURATION
        
        query = (
            update(User)
            .where(User.tid == referrer_tid)
            .values(
                refscount=User.refscount + 1,
                global_activity_until=new_global_until,
            )
        )
        await self.session.execute(query)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при обновлении реферера tid={referrer_tid}: {e}")
            raise e

    # === Реферальная система ===

    async def get_referrer(self, user: User) -> Optional[User]:
        """Получить наставника пользователя."""
        if not user.isref:
            return None
        return await self.get_by_tid(user.isref)

    async def get_referrals(self, tid: int, limit: int = 100) -> list[User]:
        """Получить список рефералов пользователя."""
        query = (
            select(User)
            .where(User.isref == tid)
            .order_by(User.regtime.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_referrals_count(self, tid: int) -> int:
        """Получить количество рефералов (из кэша)."""
        user = await self.get_by_tid(tid)
        if user:
            return user.refscount
        return 0

    async def get_upline(self, tid: int, depth: int = 100) -> list[User]:
        """
        Получить цепочку наставников вверх (для компрессии).
        
        Args:
            tid: Telegram ID пользователя
            depth: Максимальная глубина поиска
            
        Returns:
            Список наставников от ближайшего к дальнему
        """
        upline = []
        current_tid = tid
        
        for _ in range(depth):
            user = await self.get_by_tid(current_tid)
            if not user or not user.isref:
                break
            
            referrer = await self.get_by_tid(user.isref)
            if not referrer:
                break
                
            upline.append(referrer)
            current_tid = referrer.tid
        
        return upline

    # === Система активности ===

    async def press_heartbeat(self, tid: int) -> bool:
        """
        Нажатие кнопки 'Я тут' — продление на 48 часов.
        
        Returns:
            True если успешно, False если пользователь забанен
        """
        user = await self.get_by_tid(tid)
        if not user:
            return False
        
        # Нельзя нажимать если забанен
        if user.is_banned:
            return False
        
        now = int(time.time())
        new_heartbeat = now + HEARTBEAT_DURATION
        
        query = (
            update(User)
            .where(User.tid == tid)
            .values(heartbeat_until=new_heartbeat)
        )
        await self.session.execute(query)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при обновлении heartbeat tid={tid}: {e}")
            raise e
        return True

    async def update_global_activity(self, tid: int) -> bool:
        """
        Продлить глобальную активность на 30 дней.
        Вызывается при регистрации реферала.
        """
        now = int(time.time())
        new_global = now + GLOBAL_ACTIVITY_DURATION
        
        query = (
            update(User)
            .where(User.tid == tid)
            .values(global_activity_until=new_global)
        )
        result = await self.session.execute(query)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при обновлении глобальной активности tid={tid}: {e}")
            raise e
        return result.rowcount > 0

    async def is_dormant(self, tid: int) -> bool:
        """Проверка статуса 'Спящий'."""
        user = await self.get_by_tid(tid)
        if not user:
            return True
        return user.is_dormant

    async def get_active_referrals_on_level(self, tid: int, level: str) -> int:
        """
        Подсчитать активных рефералов на определённом уровне доски.
        Нужно для квалификации.
        
        TODO: Реализовать когда будет модель Tables
        """
        # Пока возвращаем общее количество рефералов
        return await self.get_referrals_count(tid)

    # === Система блокировок ===

    async def apply_ban(self, tid: int) -> int:
        """
        Наложить временную блокировку.
        Длительность зависит от счётчика нарушений.
        
        Returns:
            Количество часов блокировки
        """
        user = await self.get_by_tid(tid)
        if not user:
            return 0
        
        # Определяем длительность по количеству нарушений
        new_votes = user.votes + 1
        
        if new_votes == 1:
            duration = BAN_DURATION_FIRST  # 72 часа
        elif new_votes == 2:
            duration = BAN_DURATION_SECOND  # 144 часа
        else:
            duration = BAN_DURATION_THIRD  # 288 часов
        
        now = int(time.time())
        ban_until = now + duration
        
        query = (
            update(User)
            .where(User.tid == tid)
            .values(
                votes=new_votes,
                ban_until=ban_until,
            )
        )
        await self.session.execute(query)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при применении бана tid={tid}: {e}")
            raise e
        
        return duration // 3600  # Возвращаем часы

    async def check_ban(self, tid: int) -> bool:
        """Проверить активна ли блокировка."""
        user = await self.get_by_tid(tid)
        if not user:
            return False
        return user.is_banned

    async def pay_indulgence(self, tid: int) -> bool:
        """
        Снять блокировку после оплаты 150 USDT.
        Счётчик нарушений НЕ сбрасывается!
        """
        query = (
            update(User)
            .where(User.tid == tid)
            .values(ban_until=None)
        )
        result = await self.session.execute(query)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при снятии бана tid={tid}: {e}")
            raise e
        return result.rowcount > 0

    async def permanent_ban(self, tid: int) -> bool:
        """
        Постоянная блокировка (Blacklist).
        Применяется за вред сообществу.
        """
        query = (
            update(User)
            .where(User.tid == tid)
            .values(isblocked=True)
        )
        result = await self.session.execute(query)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при постоянной блокировке tid={tid}: {e}")
            raise e
        return result.rowcount > 0

    async def remove_from_blacklist(self, tid: int) -> bool:
        """Удалить из blacklist (только admin)."""
        query = (
            update(User)
            .where(User.tid == tid)
            .values(isblocked=False)
        )
        result = await self.session.execute(query)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при удалении из blacklist tid={tid}: {e}")
            raise e
        return result.rowcount > 0

    # === Кошелёк ===

    async def update_wallet(self, tid: int, wallet_address: str) -> bool:
        """Привязать TON кошелёк к пользователю."""
        query = (
            update(User)
            .where(User.tid == tid)
            .values(wallet_address=wallet_address)
        )
        result = await self.session.execute(query)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при обновлении кошелька tid={tid}: {e}")
            raise e
        return result.rowcount > 0

    async def get_by_wallet(self, wallet_address: str) -> Optional[User]:
        """Найти пользователя по адресу кошелька."""
        query = select(User).where(User.wallet_address == wallet_address)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    # === Утилиты ===

    def _generate_reflink(self, tid: int) -> str:
        """Генерация уникального реферального кода."""
        return f"dp_{tid}"


# Вспомогательная функция
async def get_user_service(session: AsyncSession) -> UserService:
    """Фабрика для создания UserService."""
    return UserService(session)
