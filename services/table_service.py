"""
Сервис управления досками (Tables).
Объединяет лучшие практики: полная функциональность + умные алгоритмы.
"""
import time
from typing import Optional, List, Tuple
from enum import Enum

from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.table import Table, TableStatus, LEVELS, PAYMENT_TIMEOUT
from models.user import User
from services.user_service import UserService
from utils.send_message_utils import alert


class JoinResult(str, Enum):
    """Результаты попытки присоединения к доске."""
    SUCCESS = "SUCCESS"
    USER_ALREADY_ON_LEVEL = "USER_ALREADY_ON_LEVEL"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    TABLE_CLOSED = "TABLE_CLOSED"
    NO_SLOTS = "NO_SLOTS"
    ALREADY_ON_TABLE = "ALREADY_ON_TABLE"
    USER_BLOCKED = "USER_BLOCKED"
    USER_DORMANT = "USER_DORMANT"


class TableService:
    """Сервис управления досками."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_service = UserService(session)  # Композиция (идея Gemini)

    # ===========================================
    # ПРОВЕРКИ
    # ===========================================

    async def is_user_on_level(self, tid: int, level: int) -> bool:
        """
        Проверить находится ли пользователь на доске этого уровня.
        Критично: нельзя быть на двух досках одного уровня!
        """
        query = select(Table.id).where(
            and_(
                Table.level == level,
                Table.isactive == True,
                Table.status != TableStatus.CLOSED.value,
                or_(
                    Table.rec == tid,
                    Table.crl == tid, Table.crr == tid,
                    Table.stl1 == tid, Table.stl2 == tid,
                    Table.str3 == tid, Table.str4 == tid,
                    Table.dl1 == tid, Table.dl2 == tid,
                    Table.dl3 == tid, Table.dl4 == tid,
                    Table.dr5 == tid, Table.dr6 == tid,
                    Table.dr7 == tid, Table.dr8 == tid,
                )
            )
        ).limit(1)
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def can_user_join(self, tid: int, level: int) -> Tuple[bool, str]:
        """
        Комплексная проверка может ли пользователь сесть на доску.
        
        Returns:
            Tuple[can_join, reason]
        """
        user = await self.user_service.get_by_tid(tid)
        
        if not user:
            return False, JoinResult.USER_NOT_FOUND.value
        
        if user.isblocked:
            return False, JoinResult.USER_BLOCKED.value
        
        if user.is_banned:
            return False, JoinResult.USER_BLOCKED.value
        
        # TODO: Раскомментировать когда активность будет обязательной
        # if user.is_dormant:
        #     return False, JoinResult.USER_DORMANT.value
        
        if await self.is_user_on_level(tid, level):
            return False, JoinResult.USER_ALREADY_ON_LEVEL.value
        
        return True, "OK"

    # ===========================================
    # СОЗДАНИЕ ДОСКИ
    # ===========================================

    async def create_table(
        self,
        level: int,
        creator_tid: int,
        parent_id: Optional[int] = None,
        split_side: Optional[str] = None,
    ) -> Table:
        """
        Создать новую доску.
        
        Args:
            level: Уровень доски (1-13)
            creator_tid: tid создателя (станет Receiver)
            parent_id: ID родительской доски (при разделении)
            split_side: Сторона отделения ('left'/'right')
            
        Returns:
            Созданная Table
        """
        table = Table(
            level=level,
            parent_id=parent_id,
            split_side=split_side,
            rec=creator_tid,
            status=TableStatus.WAITING.value,
            isactive=True,
            gifts_received=0,
        )
        
        self.session.add(table)
        try:
            await self.session.commit()
            await self.session.refresh(table)
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при создании доски level={level} creator={creator_tid}: {e}")
            raise e
        
        return table

    async def create_genesis_table(self, level: int, admin_tid: int) -> Table:
        """Создать первую доску системы (для админа)."""
        return await self.create_table(level=level, creator_tid=admin_tid)

    # ===========================================
    # ПОИСК ДОСКИ
    # ===========================================

    async def find_table_for_user(
        self,
        user_tid: int,
        level: int,
    ) -> Tuple[Optional[Table], str]:
        """
        Найти подходящую доску для пользователя.
        
        Алгоритм компрессии (из Whitepaper):
        1. Проверка: уже на уровне?
        2. Доска наставника
        3. Вверх по цепочке наставников (до 100 уровней)
        4. Глобальный перелив (FIFO)
        
        Returns:
            Tuple[Table, reason]
        """
        # Шаг 0: Проверки
        can_join, reason = await self.can_user_join(user_tid, level)
        if not can_join:
            return None, reason
        
        user = await self.user_service.get_by_tid(user_tid)
        
        # Шаг 1: Получаем цепочку наставников
        upline = await self.user_service.get_upline(user_tid, depth=100)
        
        # Шаг 2: Ищем доску по цепочке наставников
        for mentor in upline:
            # Пропускаем спящих наставников (компрессия)
            # TODO: Раскомментировать когда активность обязательна
            # if mentor.is_dormant:
            #     continue
            
            table = await self._find_receiver_table(mentor.tid, level)
            if table and table.empty_slots_total > 0:
                return table, f"MENTOR_{mentor.tid}"
        
        # Шаг 3: Глобальный перелив (самые старые доски первыми - FIFO)
        table = await self._find_any_open_table(level)
        if table:
            return table, "GLOBAL_SPILLOVER"
        
        return None, "NO_TABLES_AVAILABLE"

    async def find_receiver_table(
        self,
        receiver_tid: int,
        level: int,
    ) -> Optional[Table]:
        """Найти активную доску где tid — получатель (Receiver)."""
        query = select(Table).where(
            and_(
                Table.rec == receiver_tid,
                Table.level == level,
                Table.isactive == True,
                Table.status.in_([TableStatus.WAITING.value, TableStatus.ACTIVE.value]),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _find_receiver_table(
        self,
        receiver_tid: int,
        level: int,
    ) -> Optional[Table]:
        """Приватный метод (для внутреннего использования)."""
        return await self.find_receiver_table(receiver_tid, level)

    async def _find_any_open_table(self, level: int) -> Optional[Table]:
        """
        Найти любую открытую доску (глобальный перелив).
        Приоритет: самые старые (FIFO) + почти заполненные.
        """
        query = (
            select(Table)
            .where(
                and_(
                    Table.level == level,
                    Table.isactive == True,
                    Table.status.in_([TableStatus.WAITING.value, TableStatus.ACTIVE.value]),
                    # Хотя бы одно место свободно
                    or_(
                        Table.dl1 == None, Table.dl2 == None,
                        Table.dl3 == None, Table.dl4 == None,
                        Table.dr5 == None, Table.dr6 == None,
                        Table.dr7 == None, Table.dr8 == None,
                    )
                )
            )
            .order_by(
                Table.gifts_received.desc(),  # Приоритет заполненным
                Table.created_at.asc(),       # Потом по старшинству
            )
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    # ===========================================
    # РАЗМЕЩЕНИЕ НА ДОСКЕ
    # ===========================================

    async def join_table(
        self,
        table_id: int,
        user_tid: int,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Посадить пользователя на доску как дарителя.
        
        Args:
            table_id: ID доски
            user_tid: tid пользователя
            
        Returns:
            Tuple[success, reason, slot_name]
        """
        table = await self.get_by_id(table_id)
        if not table:
            return False, JoinResult.TABLE_NOT_FOUND.value, None
        
        if not table.isactive:
            return False, JoinResult.TABLE_CLOSED.value, None
        
        if table.status == TableStatus.CLOSED.value:
            return False, JoinResult.TABLE_CLOSED.value, None
        
        # Проверяем что пользователь не на этой доске
        if await self._is_user_on_table(table, user_tid):
            return False, JoinResult.ALREADY_ON_TABLE.value, None
        
        # Проверяем что не на другой доске этого уровня
        if await self.is_user_on_level(user_tid, table.level):
            return False, JoinResult.USER_ALREADY_ON_LEVEL.value, None
        
        # Умная балансировка: заполняем сторону где МЕНЬШЕ людей (идея Gemini)
        # Это ускоряет разделение!
        prefer_left = table.empty_slots_left <= table.empty_slots_right
        
        slot = table.get_first_empty_slot(prefer_left=prefer_left)
        if not slot:
            # Пробуем другую сторону
            slot = table.get_first_empty_slot(prefer_left=not prefer_left)
        
        if not slot:
            return False, JoinResult.NO_SLOTS.value, None
        
        # Занимаем место
        now = int(time.time())
        deadline = now + PAYMENT_TIMEOUT
        
        setattr(table, slot, user_tid)
        setattr(table, f"{slot}_deadline", deadline)
        setattr(table, f"{slot}_pay", False)
        
        # Обновляем статус доски
        if table.status == TableStatus.WAITING.value:
            table.status = TableStatus.ACTIVE.value
        
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при присоединении к доске table_id={table_id} user={user_tid}: {e}")
            raise e
        
        return True, JoinResult.SUCCESS.value, slot

    async def _is_user_on_table(self, table: Table, tid: int) -> bool:
        """Проверить находится ли пользователь на этой доске."""
        positions = [
            table.rec, table.crl, table.crr,
            table.stl1, table.stl2, table.str3, table.str4,
            table.dl1, table.dl2, table.dl3, table.dl4,
            table.dr5, table.dr6, table.dr7, table.dr8,
        ]
        return tid in positions

    async def leave_table(
        self,
        table_id: int,
        user_tid: int,
    ) -> Tuple[bool, str]:
        """
        Покинуть доску (только для дарителей до оплаты).
        
        Returns:
            Tuple[success, reason]
        """
        table = await self.get_by_id(table_id)
        if not table:
            return False, "TABLE_NOT_FOUND"
        
        donor_slots = ['dl1', 'dl2', 'dl3', 'dl4', 'dr5', 'dr6', 'dr7', 'dr8']
        
        for slot in donor_slots:
            if getattr(table, slot) == user_tid:
                # Проверяем не оплатил ли уже
                if getattr(table, f"{slot}_pay"):
                    return False, "ALREADY_PAID"
                
                # Освобождаем место
                setattr(table, slot, None)
                setattr(table, f"{slot}_deadline", None)
                setattr(table, f"{slot}_pay", False)
                
                try:
                    await self.session.commit()
                except IntegrityError as e:
                    await self.session.rollback()
                    await alert(f"Ошибка при покидании доски table_id={table_id} user={user_tid}: {e}")
                    raise e
                return True, f"LEFT_{slot.upper()}"
        
        return False, "NOT_A_DONOR"

    # ===========================================
    # ПОДТВЕРЖДЕНИЕ ОПЛАТЫ
    # ===========================================

    async def confirm_payment(
        self,
        table_id: int,
        donor_tid: int,
        tx_hash: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Подтвердить подарок от дарителя.
        
        Args:
            table_id: ID доски
            donor_tid: tid дарителя
            tx_hash: Хэш транзакции
            
        Returns:
            Tuple[success, message, split_ready_side]
        """
        table = await self.get_by_id(table_id)
        if not table:
            return False, "TABLE_NOT_FOUND", None
        
        # Ищем дарителя
        donor_slots = ['dl1', 'dl2', 'dl3', 'dl4', 'dr5', 'dr6', 'dr7', 'dr8']
        slot_found = None
        
        for slot in donor_slots:
            if getattr(table, slot) == donor_tid:
                slot_found = slot
                break
        
        if not slot_found:
            return False, "DONOR_NOT_FOUND", None
        
        # Проверяем не оплачен ли уже
        if getattr(table, f"{slot_found}_pay"):
            return False, "ALREADY_CONFIRMED", None
        
        # Подтверждаем оплату
        setattr(table, f"{slot_found}_pay", True)
        table.gifts_received += 1
        
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при подтверждении оплаты table_id={table_id} donor={donor_tid}: {e}")
            raise e
        
        # Проверяем готовность к разделению
        split_side = None
        if table.can_split_left:
            split_side = "left"
        elif table.can_split_right:
            split_side = "right"
        
        msg = f"GIFT_{table.gifts_received}_OF_8"
        if split_side:
            msg += f"_READY_SPLIT_{split_side.upper()}"
        
        return True, msg, split_side

    # ===========================================
    # РАЗДЕЛЕНИЕ ДОСКИ
    # ===========================================

    async def split_table(
        self,
        table_id: int,
        side: str,
    ) -> Tuple[bool, str, Optional[Table]]:
        """
        Разделить доску — создать новую от указанной стороны.
        
        Логика:
        - Creator → Receiver новой доски
        - Builders → Creators
        - Donors → Builders
        - 8 новых мест для Donors
        
        Args:
            table_id: ID родительской доски
            side: 'left' или 'right'
            
        Returns:
            Tuple[success, reason, new_table]
        """
        table = await self.get_by_id(table_id)
        if not table:
            return False, "TABLE_NOT_FOUND", None
        
        if side == "left":
            if not table.can_split_left:
                return False, "LEFT_NOT_READY", None
            
            new_rec = table.crl
            new_crl = table.stl1
            new_crr = table.stl2
            new_stl1 = table.dl1
            new_stl2 = table.dl2
            new_str3 = table.dl3
            new_str4 = table.dl4
            
        elif side == "right":
            if not table.can_split_right:
                return False, "RIGHT_NOT_READY", None
            
            new_rec = table.crr
            new_crl = table.str3
            new_crr = table.str4
            new_stl1 = table.dr5
            new_stl2 = table.dr6
            new_str3 = table.dr7
            new_str4 = table.dr8
            
        else:
            return False, "INVALID_SIDE", None
        
        # Создаём новую доску
        new_table = Table(
            level=table.level,
            parent_id=table.id,
            split_side=side,
            status=TableStatus.WAITING.value,
            isactive=True,
            gifts_received=0,
            rec=new_rec,
            crl=new_crl,
            crr=new_crr,
            stl1=new_stl1,
            stl2=new_stl2,
            str3=new_str3,
            str4=new_str4,
        )
        
        self.session.add(new_table)
        
        # Очищаем отделившуюся сторону
        if side == "left":
            table.crl = None
            table.stl1 = None
            table.stl2 = None
            table.dl1 = None
            table.dl2 = None
            table.dl3 = None
            table.dl4 = None
            table.dl1_pay = False
            table.dl2_pay = False
            table.dl3_pay = False
            table.dl4_pay = False
            table.dl1_deadline = None
            table.dl2_deadline = None
            table.dl3_deadline = None
            table.dl4_deadline = None
        else:
            table.crr = None
            table.str3 = None
            table.str4 = None
            table.dr5 = None
            table.dr6 = None
            table.dr7 = None
            table.dr8 = None
            table.dr5_pay = False
            table.dr6_pay = False
            table.dr7_pay = False
            table.dr8_pay = False
            table.dr5_deadline = None
            table.dr6_deadline = None
            table.dr7_deadline = None
            table.dr8_deadline = None
        
        # Закрываем если все 8 подарков получены
        if table.is_complete:
            table.status = TableStatus.CLOSED.value
            table.isactive = False
            table.closed_at = int(time.time())
        
        try:
            await self.session.commit()
            await self.session.refresh(new_table)
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при разделении доски table_id={table_id} side={side}: {e}")
            raise e
        
        return True, f"SPLIT_{side.upper()}_TABLE_{new_table.id}", new_table

    # ===========================================
    # ПОЛУЧЕНИЕ ДАННЫХ
    # ===========================================

    async def get_by_id(self, table_id: int) -> Optional[Table]:
        """Получить доску по ID."""
        query = select(Table).where(Table.id == table_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_tables(
        self,
        user_tid: int,
        active_only: bool = True,
    ) -> List[Table]:
        """Получить все доски пользователя."""
        conditions = [
            or_(
                Table.rec == user_tid,
                Table.crl == user_tid, Table.crr == user_tid,
                Table.stl1 == user_tid, Table.stl2 == user_tid,
                Table.str3 == user_tid, Table.str4 == user_tid,
                Table.dl1 == user_tid, Table.dl2 == user_tid,
                Table.dl3 == user_tid, Table.dl4 == user_tid,
                Table.dr5 == user_tid, Table.dr6 == user_tid,
                Table.dr7 == user_tid, Table.dr8 == user_tid,
            )
        ]
        
        if active_only:
            conditions.append(Table.isactive == True)
        
        query = (
            select(Table)
            .where(and_(*conditions))
            .order_by(Table.level, Table.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_user_position(self, table: Table, user_tid: int) -> Optional[str]:
        """Определить позицию пользователя на доске."""
        positions = {
            'rec': table.rec,
            'crl': table.crl, 'crr': table.crr,
            'stl1': table.stl1, 'stl2': table.stl2,
            'str3': table.str3, 'str4': table.str4,
            'dl1': table.dl1, 'dl2': table.dl2,
            'dl3': table.dl3, 'dl4': table.dl4,
            'dr5': table.dr5, 'dr6': table.dr6,
            'dr7': table.dr7, 'dr8': table.dr8,
        }
        
        for pos, tid in positions.items():
            if tid == user_tid:
                return pos
        return None

    async def get_position_name(self, position: str) -> str:
        """Человекочитаемое название позиции."""
        names = {
            'rec': '🎁 Получатель',
            'crl': '⭐ Создатель (Л)',
            'crr': '⭐ Создатель (П)',
            'stl1': '🔨 Строитель 1',
            'stl2': '🔨 Строитель 2',
            'str3': '🔨 Строитель 3',
            'str4': '🔨 Строитель 4',
            'dl1': '🎀 Даритель 1',
            'dl2': '🎀 Даритель 2',
            'dl3': '🎀 Даритель 3',
            'dl4': '🎀 Даритель 4',
            'dr5': '🎀 Даритель 5',
            'dr6': '🎀 Даритель 6',
            'dr7': '🎀 Даритель 7',
            'dr8': '🎀 Даритель 8',
        }
        return names.get(position, position)

    # ===========================================
    # УПРАВЛЕНИЕ ТАЙМЕРАМИ
    # ===========================================

    async def get_expired_donors(self, table_id: int) -> List[Tuple[str, int]]:
        """Получить дарителей с истёкшим таймером оплаты."""
        table = await self.get_by_id(table_id)
        if not table:
            return []
        
        now = int(time.time())
        expired = []
        
        donor_slots = ['dl1', 'dl2', 'dl3', 'dl4', 'dr5', 'dr6', 'dr7', 'dr8']
        
        for slot in donor_slots:
            tid = getattr(table, slot)
            deadline = getattr(table, f"{slot}_deadline")
            is_paid = getattr(table, f"{slot}_pay")
            
            if tid and deadline and not is_paid and now > deadline:
                expired.append((slot, tid))
        
        return expired

    async def kick_donor(
        self,
        table_id: int,
        slot: str,
        apply_ban: bool = True,
    ) -> Tuple[bool, int]:
        """
        Удалить дарителя за просрочку таймера.
        
        Args:
            table_id: ID доски
            slot: Слот дарителя
            apply_ban: Применить блокировку?
            
        Returns:
            Tuple[success, kicked_tid]
        """
        table = await self.get_by_id(table_id)
        if not table:
            return False, 0
        
        tid = getattr(table, slot)
        if not tid:
            return False, 0
        
        # Очищаем место
        setattr(table, slot, None)
        setattr(table, f"{slot}_deadline", None)
        setattr(table, f"{slot}_pay", False)
        
        # Применяем блокировку
        if apply_ban:
            hours = await self.user_service.apply_ban(tid)
        
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            await alert(f"Ошибка при удалении дарителя table_id={table_id} slot={slot}: {e}")
            raise e
        
        return True, tid

    async def get_tables_stats(self, level: int) -> dict:
        """Статистика досок на уровне."""
        # Активные
        active_query = select(func.count(Table.id)).where(
            and_(Table.level == level, Table.isactive == True)
        )
        active_result = await self.session.execute(active_query)
        active_count = active_result.scalar() or 0
        
        # Закрытые
        closed_query = select(func.count(Table.id)).where(
            and_(Table.level == level, Table.status == TableStatus.CLOSED.value)
        )
        closed_result = await self.session.execute(closed_query)
        closed_count = closed_result.scalar() or 0
        
        return {
            "level": level,
            "level_name": LEVELS.get(level, {}).get("name", "Unknown"),
            "active": active_count,
            "closed": closed_count,
            "total": active_count + closed_count,
        }


# Фабрика
async def get_table_service(session: AsyncSession) -> TableService:
    """Создать TableService."""
    return TableService(session)
