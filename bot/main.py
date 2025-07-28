import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from telebot import TeleBot, types
from telebot.async_telebot import AsyncTeleBot
from telebot.apihelper import ApiException
from handlers import register_handlers
from db import test_database_connection
from utils import *
from message_utils import message_manager

# Настройка логирования
logger = setup_logging()

# Команды бота
BOT_COMMANDS = {
    "/start": "🏠 Меню бота",
    "/new_giveaway": "🎁 Создать розыгрыш",
    "/my_giveaways": "📋 Мои розыгрыши",
    "/my_channels": "📺 Мои каналы",
    "/help": "❓ Справка",
    "/support": "🆘 Поддержка"
}


async def setup_bot_commands(bot: AsyncTeleBot):
    """Настройка команд бота"""
    try:
        commands = [
            types.BotCommand(cmd, desc) for cmd, desc in BOT_COMMANDS.items()
        ]
        await bot.set_my_commands(commands)
        log_info(logger, "✅ Команды бота успешно настроены")
    except Exception as e:
        log_error(logger, e, "настройка команд бота")

async def init_bot() -> AsyncTeleBot:
    """Инициализация бота"""
    load_dotenv()
    TOKEN = os.getenv('TELEGRAM_TOKEN')

    if not TOKEN:
        log_error(logger, "TELEGRAM_TOKEN не найден в переменных окружения", "конфигурация")
        sys.exit(1)

    try:
        bot = AsyncTeleBot(TOKEN)
        bot.logger = logger  # Добавляем logger к объекту бота
        
        # Получаем информацию о боте для логирования
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            log_bot_start(logger, token_status=True, bot_username=bot_username)
        except Exception as e:
            log_error(logger, e, "получение информации о боте")
            log_bot_start(logger, token_status=True)  # Запускаем без username
            
        return bot
        
    except Exception as e:
        log_error(logger, e, "инициализация бота")
        sys.exit(1)

async def run_bot():
    """Запуск бота с обработкой ошибок"""
    max_retries = 5
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            # Инициализируем бота
            bot = await init_bot()
            
            # Проверка подключения к базе данных
            if not test_database_connection(logger):
                log_error(logger, "Не удалось подключиться к базе данных", "запуск")
                log_info(logger, "Бот будет работать без базы данных")

            # Регистрируем обработчики
            register_handlers(bot)
            
            # Настраиваем команды бота
            await setup_bot_commands(bot)
            
            log_info(logger, f"🚀 Бот готов к работе")
            await bot.polling(none_stop=True, timeout=60)
            
        except ApiException as e:
            log_error(logger, e, f"API Telegram (попытка {attempt + 1})")
            if attempt < max_retries - 1:
                log_info(logger, f"Повторная попытка через {retry_delay} секунд...")
                await asyncio.sleep(retry_delay)
            else:
                log_error(logger, "Превышено максимальное количество попыток подключения", "критическая ошибка")
                break
        except KeyboardInterrupt:
            log_bot_stop(logger)
            break
        except Exception as e:
            log_error(logger, e, f"неожиданная ошибка (попытка {attempt + 1})")
            if attempt < max_retries - 1:
                log_info(logger, f"Повторная попытка через {retry_delay} секунд...")
                await asyncio.sleep(retry_delay)
            else:
                log_error(logger, "Превышено максимальное количество попыток", "критическая ошибка")
                break

if __name__ == '__main__':
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log_bot_stop(logger)
    except Exception as e:
        log_error(logger, e, "критическая ошибка")
        sys.exit(1)