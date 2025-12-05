"""
Утилиты для отправки сообщений.
Функция alert() для логирования ошибок в чат логов.
"""
import logging

from bot_instance import bot
from config import LOGCHAT

logger = logging.getLogger(__name__)


async def alert(text: str) -> None:
    """
    Отправить сообщение в чат логов.
    
    Используется для логирования ошибок и важных событий.
    Если LOGCHAT не настроен, сообщение выводится в консоль.
    
    Args:
        text: Текст сообщения для отправки
    """
    try:
        if LOGCHAT:
            await bot.send_message(chat_id=LOGCHAT, text=text)
        else:
            logger.warning(f"LOGCHAT не настроен. Сообщение: {text}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в LOGCHAT: {e}")
        logger.error(f"Текст сообщения: {text}")
