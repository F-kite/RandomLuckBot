import os
import sys
import time
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.apihelper import ApiException
from handlers import register_handlers
from db import test_database_connection
from utils import *

# Настройка логирования
logger = setup_logging()

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

if not TOKEN:
    log_error(logger, "TELEGRAM_TOKEN не найден в переменных окружения", "конфигурация")
    sys.exit(1)

try:
    bot = TeleBot(TOKEN)
    bot.logger = logger  # Добавляем logger к объекту бота
    
    # Получаем информацию о боте для логирования
    try:
        bot_info = bot.get_me()
        bot_username = bot_info.username
        log_bot_start(logger, token_status=True, bot_username=bot_username)
    except Exception as e:
        log_error(logger, e, "получение информации о боте")
        log_bot_start(logger, token_status=True)  # Запускаем без username
        
except Exception as e:
    log_error(logger, e, "инициализация бота")
    sys.exit(1)

# Проверка подключения к базе данных
log_info(logger, "Проверка подключения к базе данных...")
if not test_database_connection(logger):
    log_error(logger, "Не удалось подключиться к базе данных", "запуск")
    log_info(logger, "Бот будет работать без базы данных")

register_handlers(bot)

@bot.message_handler(commands=['start'])
def start_handler(message):
    try:
        log_command(logger, message.from_user.id, message.from_user.username, 'start')
        bot.send_message(message.chat.id, 'Привет! Я бот-рандомайзер для розыгрышей.')
    except Exception as e:
        log_error(logger, e, f"обработка команды /start от пользователя {message.from_user.id}")

def run_bot():
    """Запуск бота с обработкой ошибок"""
    max_retries = 5
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            log_info(logger, f"Попытка запуска бота #{attempt + 1}")
            bot.polling(none_stop=True, timeout=60)
        except ApiException as e:
            log_error(logger, e, f"API Telegram (попытка {attempt + 1})")
            if attempt < max_retries - 1:
                log_info(logger, f"Повторная попытка через {retry_delay} секунд...")
                time.sleep(retry_delay)
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
                time.sleep(retry_delay)
            else:
                log_error(logger, "Превышено максимальное количество попыток", "критическая ошибка")
                break

if __name__ == '__main__':
    run_bot() 