"""
Модель пользователя.
Хранит данные пользователей Telegram и реферальную информацию.
"""
import time
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

# Константы времени (в секундах)
GLOBAL_ACTIVITY_DURATION = 30 * 24 * 60 * 60  # 30 дней
HEARTBEAT_DURATION = 48 * 60 * 60  # 48 часов
BAN_DURATION_FIRST = 72 * 60 * 60  # 72 часа (1-е нарушение)
BAN_DURATION_SECOND = 144 * 60 * 60  # 144 часа (2-е нарушение)
BAN_DURATION_THIRD = 288 * 60 * 60  # 288 часов (3+ нарушение)


class User(Base):
    """Модель пользователя системы."""
    
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    # Первичный ключ
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # Telegram данные
    tid: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    fullname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # TON Wallet
    wallet_address: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    
    # Реферальная система (без ForeignKey — связь через код)
    isref: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    reflink: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    refscount: Mapped[int] = mapped_column(Integer, default=0)
    
    # Время регистрации (Unix timestamp)
    regtime: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Флаги статусов
    isactive: Mapped[bool] = mapped_column(Boolean, default=True)
    isadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    isblocked: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Система временных блокировок
    ban_until: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    votes: Mapped[int] = mapped_column(Integer, default=0)
    
    # Глобальная активность (30 дней)
    global_activity_until: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Текущая активность "Я тут" (48 часов)
    heartbeat_until: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<User tid={self.tid} username={self.username}>"

    # === Properties ===

    @property
    def display_name(self) -> str:
        """Отображаемое имя пользователя."""
        if self.fullname:
            return self.fullname
        if self.username:
            return f"@{self.username}"
        return f"User {self.tid}"

    @property
    def referral_link(self) -> str:
        """Полная реферальная ссылка для Telegram."""
        return f"https://t.me/DP_Sma_test_bot?start={self.reflink}"

    @property
    def is_globally_active(self) -> bool:
        """Проверка глобальной активности (30 дней)."""
        if not self.global_activity_until:
            return False
        return int(time.time()) < self.global_activity_until

    @property
    def is_heartbeat_active(self) -> bool:
        """Проверка текущей активности (48ч)."""
        if not self.heartbeat_until:
            return False
        return int(time.time()) < self.heartbeat_until

    @property
    def is_dormant(self) -> bool:
        """Проверка статуса 'Спящий'."""
        return not self.is_globally_active or not self.is_heartbeat_active

    @property
    def is_banned(self) -> bool:
        """Проверка временной блокировки."""
        if not self.ban_until:
            return False
        return int(time.time()) < self.ban_until

    @property
    def can_participate(self) -> bool:
        """Может ли участвовать в системе."""
        return not self.is_dormant and not self.is_banned and not self.isblocked

    @property
    def ban_remaining_hours(self) -> int:
        """Часов до разблокировки."""
        if not self.ban_until:
            return 0
        remaining = self.ban_until - int(time.time())
        return max(0, remaining // 3600)

    @property
    def global_activity_remaining_days(self) -> int:
        """Дней глобальной активности."""
        if not self.global_activity_until:
            return 0
        remaining = self.global_activity_until - int(time.time())
        return max(0, remaining // 86400)

    @property
    def heartbeat_remaining_hours(self) -> int:
        """Часов текущей активности."""
        if not self.heartbeat_until:
            return 0
        remaining = self.heartbeat_until - int(time.time())
        return max(0, remaining // 3600)
