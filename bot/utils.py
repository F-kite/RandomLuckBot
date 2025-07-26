import logging
import os
from datetime import datetime
import pytz

def setup_logging():
    """Настройка логирования для бота"""
    # Создаем директорию для логов если её нет
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Путь к файлу логов
    log_file = os.path.join(log_dir, 'logs.txt')
    
    # Настройка форматирования с московским временем
    class MoscowTimeFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            moscow_tz = pytz.timezone('Europe/Moscow')
            dt = datetime.fromtimestamp(record.created, moscow_tz)
            if datefmt:
                return dt.strftime(datefmt)
            else:
                return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    formatter = MoscowTimeFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Настройка логгера
    logger = logging.getLogger('RandomLuckBot')
    logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики
    logger.handlers.clear()
    
    # Обработчик для файла
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Добавляем обработчики к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def log_database_connection(logger, success=True, error=None):
    """Логирование состояния подключения к базе данных"""
    if success:
        logger.info("✅ Успешное подключение к базе данных PostgreSQL")
    else:
        logger.error(f"❌ Ошибка подключения к базе данных: {error}")

def log_bot_start(logger, token_status=True, bot_username=None):
    """Логирование запуска бота"""
    if token_status:
        if bot_username:
            logger.info(f"🚀 Бот запускается... @{bot_username}")
        else:
            logger.info("🚀 Бот запускается...")
        logger.info("📱 Telegram Bot API подключен")
    else:
        logger.error("❌ Ошибка: Не удалось получить токен бота")

def log_bot_stop(logger):
    """Логирование остановки бота"""
    logger.info("🛑 Бот остановлен")

def log_command(logger, user_id, username, command):
    """Логирование команд пользователей"""
    logger.info(f"👤 Пользователь {username} (ID: {user_id}) выполнил команду: /{command}")

def log_error(logger, error, context=""):
    """Логирование ошибок"""
    logger.error(f"❌ Ошибка {context}: {str(error)}")

def log_info(logger, message):
    """Логирование информационных сообщений"""
    logger.info(f"ℹ️ {message}") 