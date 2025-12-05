"""
Модель игровой доски (Table).
Реализует структуру 15-местной матрицы: REC, CR, ST, D.
"""
import time
from typing import Optional, List
from enum import Enum

from sqlalchemy import BigInteger, Boolean, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# === КОНФИГУРАЦИЯ УРОВНЕЙ ===
LEVELS = {
    1: {"name": "Start", "amount": 10},
    2: {"name": "Tin", "amount": 20},
    3: {"name": "Bronze", "amount": 40},
    4: {"name": "Copper", "amount": 80},
    5: {"name": "Silver", "amount": 160},
    6: {"name": "Amber", "amount": 320},
    7: {"name": "Gold", "amount": 640},
    8: {"name": "Ruby", "amount": 1280},
    9: {"name": "Platinum", "amount": 2560},
    10: {"name": "Emerald", "amount": 5120},
    11: {"name": "Brilliant", "amount": 10240},
    12: {"name": "Sapphire", "amount": 20480},
    13: {"name": "Titan", "amount": 40960},
}

# Таймеры (секунды)
PAYMENT_TIMEOUT = 72 * 60 * 60  # 72 часа на оплату
CONFIRM_TIMEOUT = 24 * 60 * 60  # 24 часа на подтверждение (авто)


class TableStatus(str, Enum):
    """Статусы доски."""
    WAITING = "waiting"      # Ждёт дарителей
    ACTIVE = "active"        # Идут подарки
    SPLITTING = "splitting"  # В процессе разделения
    CLOSED = "closed"        # Закрыта


class Table(Base):
    """
    Модель доски.
    15 позиций: 1 REC + 2 CR + 4 ST + 8 D
    """
    
    __tablename__ = "tables"
    __table_args__ = (
        Index("idx_table_level_status", "level", "status"),
        Index("idx_table_active", "isactive"),
        {"extend_existing": True}
    )

    # === ИДЕНТИФИКАЦИЯ ===
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # Уровень доски (1-13)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    
    # Родительская доска (откуда отделились, None для корневых)
    parent_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    
    # Сторона отделения (left/right, None для корневых)
    split_side: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    
    # === ВРЕМЕННЫЕ МЕТКИ ===
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time()))
    closed_at: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # === СТАТУСЫ ===
    status: Mapped[str] = mapped_column(String(16), default=TableStatus.WAITING.value)
    isactive: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Счётчик полученных подарков (1-8)
    gifts_received: Mapped[int] = mapped_column(Integer, default=0)

    # === 15 ПОЗИЦИЙ (tid пользователей, без ForeignKey) ===
    
    # 1. Получатель (Receiver) - вершина
    rec: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    
    # 2. Создатели (Creators) - левый и правый
    crl: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    crr: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # 3. Строители (Builders) - 4 позиции
    stl1: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    stl2: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    str3: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    str4: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # 4. Дарители (Donors) - 8 позиций
    dl1: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dl2: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dl3: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dl4: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dr5: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dr6: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dr7: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dr8: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # === СТАТУСЫ ОПЛАТЫ (подарок доставлен) ===
    dl1_pay: Mapped[bool] = mapped_column(Boolean, default=False)
    dl2_pay: Mapped[bool] = mapped_column(Boolean, default=False)
    dl3_pay: Mapped[bool] = mapped_column(Boolean, default=False)
    dl4_pay: Mapped[bool] = mapped_column(Boolean, default=False)
    dr5_pay: Mapped[bool] = mapped_column(Boolean, default=False)
    dr6_pay: Mapped[bool] = mapped_column(Boolean, default=False)
    dr7_pay: Mapped[bool] = mapped_column(Boolean, default=False)
    dr8_pay: Mapped[bool] = mapped_column(Boolean, default=False)

    # === ТАЙМЕРЫ ОПЛАТЫ (Unix timestamp дедлайна) ===
    dl1_deadline: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dl2_deadline: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dl3_deadline: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dl4_deadline: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dr5_deadline: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dr6_deadline: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dr7_deadline: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dr8_deadline: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<Table id={self.id} L{self.level} rec={self.rec} gifts={self.gifts_received}/8>"

    # === PROPERTIES: Информация об уровне ===
    
    @property
    def level_name(self) -> str:
        """Название уровня."""
        return LEVELS.get(self.level, {}).get("name", "Unknown")
    
    @property
    def gift_amount(self) -> int:
        """Сумма подарка на этом уровне (USDT)."""
        return LEVELS.get(self.level, {}).get("amount", 0)

    # === PROPERTIES: Состояние доски ===

    @property
    def is_complete(self) -> bool:
        """Доска завершена (получены все 8 подарков)."""
        return self.gifts_received >= 8

    @property
    def left_donors(self) -> List[Optional[int]]:
        """Список tid дарителей слева."""
        return [self.dl1, self.dl2, self.dl3, self.dl4]
    
    @property
    def right_donors(self) -> List[Optional[int]]:
        """Список tid дарителей справа."""
        return [self.dr5, self.dr6, self.dr7, self.dr8]
    
    @property
    def left_payments(self) -> List[bool]:
        """Статусы оплаты слева."""
        return [self.dl1_pay, self.dl2_pay, self.dl3_pay, self.dl4_pay]
    
    @property
    def right_payments(self) -> List[bool]:
        """Статусы оплаты справа."""
        return [self.dr5_pay, self.dr6_pay, self.dr7_pay, self.dr8_pay]

    @property
    def is_left_full(self) -> bool:
        """Все места слева заняты."""
        return all(tid is not None for tid in self.left_donors)

    @property
    def is_right_full(self) -> bool:
        """Все места справа заняты."""
        return all(tid is not None for tid in self.right_donors)
    
    @property
    def is_left_paid(self) -> bool:
        """Все 4 дарителя слева оплатили."""
        return all(self.left_payments)

    @property
    def is_right_paid(self) -> bool:
        """Все 4 дарителя справа оплатили."""
        return all(self.right_payments)

    @property
    def can_split_left(self) -> bool:
        """Можно разделить левую сторону."""
        return self.is_left_full and self.is_left_paid

    @property
    def can_split_right(self) -> bool:
        """Можно разделить правую сторону."""
        return self.is_right_full and self.is_right_paid

    @property
    def empty_slots_left(self) -> int:
        """Количество свободных мест слева."""
        return sum(1 for tid in self.left_donors if tid is None)

    @property
    def empty_slots_right(self) -> int:
        """Количество свободных мест справа."""
        return sum(1 for tid in self.right_donors if tid is None)
    
    @property
    def empty_slots_total(self) -> int:
        """Всего свободных мест для дарителей."""
        return self.empty_slots_left + self.empty_slots_right

    @property
    def paid_count(self) -> int:
        """Количество оплаченных подарков."""
        return sum(self.left_payments) + sum(self.right_payments)

    # === METHODS: Поиск свободного места ===
    
    def get_first_empty_slot(self, prefer_left: bool = True) -> Optional[str]:
        """
        Найти первое свободное место для дарителя.
        
        Args:
            prefer_left: Приоритет левой стороны
            
        Returns:
            Имя слота ('dl1', 'dr5', etc.) или None
        """
        left_slots = [
            ("dl1", self.dl1),
            ("dl2", self.dl2),
            ("dl3", self.dl3),
            ("dl4", self.dl4),
        ]
        right_slots = [
            ("dr5", self.dr5),
            ("dr6", self.dr6),
            ("dr7", self.dr7),
            ("dr8", self.dr8),
        ]
        
        if prefer_left:
            order = left_slots + right_slots
        else:
            order = right_slots + left_slots
        
        for slot_name, tid in order:
            if tid is None:
                return slot_name
        
        return None

    def get_slot_deadline(self, slot_name: str) -> Optional[int]:
        """Получить дедлайн для слота."""
        return getattr(self, f"{slot_name}_deadline", None)
    
    def is_slot_expired(self, slot_name: str) -> bool:
        """Проверить истёк ли таймер слота."""
        deadline = self.get_slot_deadline(slot_name)
        if deadline is None:
            return False
        return int(time.time()) > deadline
