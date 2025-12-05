# 🎯 GLEB'S CODE STYLE - EXTENDED EXAMPLES

## Быстрая справка для Cursor AI

---

## 1. КАК СОЗДАВАТЬ СЕРВИС

### ✅ ПРАВИЛЬНО (стиль Глеба):
```python
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from models.user import User
from models.tables import Tables


class PaymentService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user(self, tid: int) -> User | None:
        result = await self.db.execute(select(User).where(User.tid == tid))
        return result.scalars().first()

    async def get_user_with_relations(self, tid: int) -> User | None:
        result = await self.db.execute(
            select(User)
            .where(User.tid == tid)
            .options(joinedload(User.nastavnik))
            .options(joinedload(User.sit_data))
        )
        return result.scalars().first()

    async def update_payment_status(self, tid: int, level: str) -> bool:
        user_data = await self.get_user(tid=tid)
        if not user_data:
            return False

        # Динамический доступ к полям
        pay_field = f"ispay{level}"
        setattr(user_data, pay_field, True)
        await self.db.commit()
        return True

    async def bulk_update(self, tid: int, **kwargs):
        if not kwargs:
            return
        query = (
            update(User)
            .where(User.tid == tid)
            .values(**kwargs)
            .execution_options(synchronize_session="fetch")
        )
        await self.db.execute(query)
        await self.db.commit()
```

### ❌ НЕПРАВИЛЬНО:
```python
# НЕ делай так:
class payment_service:  # ❌ snake_case для класса
    def __init__(self):  # ❌ нет db: AsyncSession
        self.session = get_session()  # ❌ глобальная функция

    def get_user(self, user_id):  # ❌ sync, user_id вместо tid, нет типов
        return self.session.query(User).filter_by(id=user_id).first()  # ❌ legacy API
```

---

## 2. КАК СОЗДАВАТЬ МОДЕЛИ

### ✅ ПРАВИЛЬНО (стиль Глеба):
```python
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    String,
)
from sqlalchemy.orm import relationship

from database import Base


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = {"extend_existing": True}  # ОБЯЗАТЕЛЬНО!

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tid = Column(BigInteger, unique=True, nullable=False)
    
    # Слитные имена для специфичных полей
    walletaddress = Column(String(100))
    isverified = Column(Boolean, default=False)
    balanceusdt = Column(BigInteger, default=0)
    
    # Стандартные временные метки
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, onupdate=datetime.utcnow)

    # Relationships с viewonly=True
    user = relationship(
        "User",
        uselist=False,
        foreign_keys=[tid],
        primaryjoin="Wallet.tid == User.tid",
        viewonly=True,
    )
```

### ❌ НЕПРАВИЛЬНО:
```python
# НЕ делай так:
class wallet(Base):  # ❌ lowercase
    __tablename__ = 'wallets'  # ❌ одинарные кавычки
    # ❌ нет __table_args__
    
    id = Column(Integer)  # ❌ Integer вместо BigInteger
    user_id = Column(Integer)  # ❌ user_id вместо tid
    wallet_address = Column(String)  # ❌ snake_case в имени колонки
    is_verified = Column(Boolean)  # ❌ snake_case
```

---

## 3. КАК ПИСАТЬ ЗАПРОСЫ

### SELECT с eager loading:
```python
# Простой запрос
result = await self.db.execute(select(User).where(User.tid == tid))
user = result.scalars().first()

# С одной связью
result = await self.db.execute(
    select(User)
    .where(User.tid == tid)
    .options(joinedload(User.nastavnik))
)

# С множеством связей (каждый .options на новой строке)
result = await self.db.execute(
    select(Tables)
    .where(Tables.tableid == table_id)
    .options(selectinload(Tables.dl1_data).selectinload(User.sit_data))
    .options(selectinload(Tables.dl1_data).selectinload(User.nastavnik))
    .options(selectinload(Tables.dl2_data).selectinload(User.sit_data))
    .options(selectinload(Tables.dl2_data).selectinload(User.nastavnik))
)
```

### UPDATE через **kwargs:
```python
async def update_user(self, tid: int, **kwargs):
    if not kwargs:
        return
    query = (
        update(User)
        .where(User.tid == tid)
        .values(**kwargs)
        .execution_options(synchronize_session="fetch")
    )
    await self.db.execute(query)
    await self.db.commit()

# Использование:
await self.update_user(tid=12345, ispaystart=True, mystatusstart="donor")
```

### INSERT с обработкой ошибок:
```python
from sqlalchemy.exc import IntegrityError

async def create_wallet(self, tid: int, address: str) -> Wallet:
    new_wallet = Wallet(tid=tid, walletaddress=address)
    self.db.add(new_wallet)
    try:
        await self.db.commit()
    except IntegrityError as e:
        await self.db.rollback()
        raise e
    return new_wallet
```

---

## 4. КАК РАБОТАТЬ С ДИНАМИЧЕСКИМИ ПОЛЯМИ

```python
# Маппинг уровней
LEVEL_FIELDS = {
    "start": {"pay": "ispaystart", "status": "mystatusstart", "sit": "nowsitstarttable"},
    "bronz": {"pay": "ispaybronz", "status": "mystatusbronz", "sit": "nowsitbronztable"},
    "silver": {"pay": "ispaysilver", "status": "mystatussilver", "sit": "nowsitsilvertable"},
    # ...
}

# Динамический доступ
async def check_payment(self, tid: int, level: str) -> bool:
    user_data = await self.get_user(tid=tid)
    if not user_data:
        return False
    
    pay_field = f"ispay{level}"
    return getattr(user_data, pay_field, False) is True

# Динамическое обновление
async def set_status(self, tid: int, level: str, status: str):
    user_data = await self.get_user(tid=tid)
    if user_data:
        status_field = f"mystatus{level}"
        setattr(user_data, status_field, status)
        await self.db.commit()
```

---

## 5. КАК ОБРАБАТЫВАТЬ ОШИБКИ

### Telegram API:
```python
from bot_instance import bot
from utils.service_utils import alert
from texts.logs import LogsTexts

async def send_notification(self, tid: int, text: str):
    try:
        await bot.send_message(chat_id=tid, text=text)
    except Exception as e:
        await alert(text=LogsTexts.user_block_bot(tid=str(tid), e=str(e)))
```

### Массовая отправка:
```python
async def broadcast(self, tids: list[int], text: str):
    success, failed = 0, 0
    for tid in tids:
        try:
            await bot.send_message(chat_id=tid, text=text)
            success += 1
        except Exception as e:
            await alert(text=f"Не отправил {tid}: {e}")
            failed += 1
    return success, failed
```

---

## 6. КАК ПИСАТЬ КОММЕНТАРИИ

```python
# ✅ Комментарии на русском
# Проверяем, оплатил ли пользователь стартовую доску
if user_data.ispaystart:
    pass

# INFO: Пояснение важного решения
# INFO: Используем joinedload вместо selectinload для единичных связей

# TODO: Задачи на будущее
# TODO: Добавить проверку на блокировку пользователя
# TODO: @glebkhyl пересмотри логику разделения

# BUG TODO: Известные баги
# BUG TODO: Иногда timer1 = None, нужна проверка

# Закомментированный код (если нужно сохранить)
# await alert(
#     text=LogsTexts.user_block_bot(tid=str(user.tid), e=str(e))
# )
```

---

## 7. КАК ИСПОЛЬЗОВАТЬ ТИПИЗАЦИЮ

```python
from typing import Any, List, Optional, Sequence, Tuple

# Возврат одного объекта или None
async def get_user(self, tid: int) -> User | None:
    ...

# Возврат списка
async def get_all_users(self) -> list[User]:
    ...

# Возврат словаря
async def get_stats(self) -> dict[str, int]:
    ...

# Возврат кортежа
async def get_user_and_table(self, tid: int) -> tuple[User | None, Tables | None]:
    ...

# Сложные типы
async def get_counts(self) -> dict[str, dict[str, int]]:
    ...
```

---

## 8. КАК СТРУКТУРИРОВАТЬ УТИЛИТЫ

```python
# utils/payment_utils.py

import time
from typing import Optional

from bot_instance import bot
from services.user_service import UserService
from texts.logs import LogsTexts
from utils.service_utils import alert


async def calculate_gift_amount(level: str) -> int:
    """Возвращает размер подарка для уровня."""
    amounts = {
        "start": 10,
        "tin": 20,
        "bronz": 40,
        "copper": 80,
        "silver": 160,
        "amber": 320,
        "gold": 640,
        "ruby": 1280,
        "platin": 2560,
        "emerald": 5120,
        "brilliant": 10240,
        "sapphire": 20480,
        "titan": 40960,
    }
    return amounts.get(level, 0)


async def notify_table_members(
    table_data,
    text: str,
    exclude_tid: Optional[int] = None,
):
    """Отправляет уведомление всем участникам доски."""
    positions = ["dl1", "dl2", "dl3", "dl4", "dr5", "dr6", "dr7", "dr8"]
    
    for pos in positions:
        tid = getattr(table_data, pos, None)
        if tid and tid != exclude_tid:
            try:
                await bot.send_message(chat_id=tid, text=text)
            except Exception as e:
                await alert(text=LogsTexts.user_block_bot(tid=str(tid), e=str(e)))
```

---

## 9. ПАТТЕРН NotificationService

```python
from aiogram import Bot

from utils.service_utils import alert
from texts.logs import LogsTexts


class NotificationService:

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_to_table(self, table_data, text: str, exclude_tid: int = None):
        tids = set()

        if table_data.leftopen:
            for field in ["dl1", "dl2", "dl3", "dl4", "stl1", "stl2", "crl1"]:
                tid = getattr(table_data, field, None)
                if tid and tid != exclude_tid:
                    tids.add(tid)

        if table_data.rightopen:
            for field in ["dr5", "dr6", "dr7", "dr8", "str3", "str4", "crr2"]:
                tid = getattr(table_data, field, None)
                if tid and tid != exclude_tid:
                    tids.add(tid)

        for user_tid in tids:
            try:
                await self.bot.send_message(chat_id=user_tid, text=text)
            except Exception as e:
                await alert(text=LogsTexts.user_block_bot(tid=str(user_tid), e=str(e)))
```

---

## 10. TIMESTAMP ПАТТЕРНЫ

```python
import time
from datetime import datetime, timedelta

# Текущий timestamp
current_ts = int(time.time())

# Через 3 дня
future_ts = int(time.time()) + 86400 * 3

# 24 часа назад
past_ts = int(time.time()) - 86400

# Проверка истечения таймера
if user_data.timer1 < int(time.time()):
    # Таймер истёк
    pass

# Форматирование для вывода
unblock_date = datetime.utcfromtimestamp(timer_end).strftime("%Y-%m-%d %H:%M")
```

---

## КРАТКАЯ ШПАРГАЛКА

| Что делаем | Как делаем |
|------------|------------|
| Создать сервис | `class XService:` + `__init__(self, db: AsyncSession)` |
| Получить запись | `result = await self.db.execute(select(Model).where(...))` → `result.scalars().first()` |
| Обновить запись | `update(Model).where(...).values(**kwargs)` |
| Eager loading | `.options(joinedload(Model.relation))` |
| Динамическое поле | `getattr(obj, f"ispay{level}", False)` |
| Обработка ошибок | `try: ... except Exception as e: await alert(...)` |
| Timestamp | `int(time.time())` |
| Debug | `ic(variable)` |
| Комментарии | На русском: `# Проверяем оплату` |

---

*Следуй этим примерам точно — и код будет неотличим от кода Глеба.*
