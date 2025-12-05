"""
Экземпляр бота (singleton).
Создает Bot instance для использования во всем проекте.
"""
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN

# Проверка наличия токена
if not BOT_TOKEN:
    sys.exit("Ошибка: BOT_TOKEN не указан в .env файле!")

# Создаем singleton экземпляр бота с HTML парсингом
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)