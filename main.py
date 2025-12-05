"""
Точка входа бота Дари Получай Smart.
"""
import asyncio
import logging

from aiogram import Dispatcher

from bot_instance import bot
from database import engine, Base

# Импорт роутеров
from handlers.start import router as start_router
from handlers.boards import router as boards_router
from handlers.admin import router as admin_router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Создание диспетчера
dp = Dispatcher()

# Регистрация роутеров
dp.include_router(start_router)
dp.include_router(boards_router)
dp.include_router(admin_router)


@dp.startup()
async def on_startup() -> None:
    """Действия при запуске бота."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ База данных подключена, таблицы созданы")


@dp.shutdown()
async def on_shutdown() -> None:
    """Действия при остановке бота."""
    await engine.dispose()
    logger.info("👋 Бот остановлен")


async def main() -> None:
    """Запуск бота."""
    logger.info("🤖 Бот Дари Получай Smart")
    logger.info("🚀 Запуск...")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())