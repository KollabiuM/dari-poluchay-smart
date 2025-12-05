"""
Конфигурация проекта.
Загружает переменные окружения из .env файла.
"""
import os
from typing import List

from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Telegram Bot
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Database
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/dbname"
)

# Logging (chat_id для отправки логов)
LOGCHAT: int = int(os.getenv("LOGCHAT", "0"))

# Admin IDs
ADMIN_IDS_STR: str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = (
    [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip()]
    if ADMIN_IDS_STR
    else []
)

# Таймеры (в секундах)
PAYMENT_TIMEOUT: int = 72 * 60 * 60       # 72 часа на оплату
CONFIRMATION_TIMEOUT: int = 24 * 60 * 60  # 24 часа на подтверждение
SEPARATIONBLOCK: int = 48 * 60 * 60       # 48 часов блокировка разделения

# Текстовый разделитель для сообщений
SEPARATOR_LINE: str = "─" * 50

# Сервисы (можно расширить позже)
SERVICES: dict = {}