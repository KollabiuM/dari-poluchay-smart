"""
Настройка базы данных.
Создает async engine, sessionmaker и Base для SQLAlchemy 2.0.
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL

# Создаем async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Установить True для отладки SQL запросов
    future=True,
)

# Создаем sessionmaker для async сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base класс для всех моделей
class Base(DeclarativeBase):
    """Базовый класс для всех SQLAlchemy моделей."""
    pass


# Функция для получения сессии (Dependency Injection)
async def get_db():
    """Генератор сессии для использования в хэндлерах."""
    async with AsyncSessionLocal() as session:
        yield session