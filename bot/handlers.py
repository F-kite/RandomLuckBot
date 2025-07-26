import telebot
from telebot import types
from models import  User, Channel, Giveaway, GiveawayChannel, GiveawayParticipant, SupportRequest
from db import SessionLocal
from utils import log_command, log_error, log_info

user_states = {}  # Для хранения промежуточных данных по chat_id


def register_handlers(bot):
    @bot.message_handler(commands=['help'])
    def help_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'help')
            bot.send_message(
                message.chat.id,
                'Доступные команды:\n'
                '/new_giveaway — создать розыгрыш\n'
                '/my_giveaways — мои розыгрыши\n'
                '/add_channel — добавить канал\n'
                '/my_channels — мои каналы\n'
                '/support — написать в поддержку'
            )
        except Exception as e:
            log_error(bot.logger, e, f"обработка команды /help от пользователя {message.from_user.id}")

    # === Создание розыгрыша ===
    @bot.message_handler(commands=['new_giveaway'])
    def new_giveaway_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'new_giveaway')
            user_states[message.chat.id] = {}
            msg = bot.send_message(message.chat.id, "Пришлите медиа для розыгрыша (фото, видео или GIF)")
            bot.register_next_step_handler(msg, process_giveaway_media)
        except Exception as e:
            log_error(bot.logger, e, f"обработка команды /new_giveaway от пользователя {message.from_user.id}")

    def process_giveaway_media(message):
        try:
            user_states[message.chat.id]['media'] = getattr(message, 'photo', None) or getattr(message, 'video', None) or getattr(message, 'document', None)
            msg = bot.send_message(message.chat.id, "Введите описание розыгрыша и приз")
            bot.register_next_step_handler(msg, process_giveaway_description)
        except Exception as e:
            log_error(bot.logger, e, f"обработка медиа для розыгрыша от пользователя {message.from_user.id}")

    def process_giveaway_description(message):
        try:
            user_states[message.chat.id]['description'] = message.text
            msg = bot.send_message(message.chat.id, "Укажите обязательные подписки (через запятую ссылки на каналы/группы) или напишите 'нет'")
            bot.register_next_step_handler(msg, process_giveaway_channels)
        except Exception as e:
            log_error(bot.logger, e, f"обработка описания розыгрыша от пользователя {message.from_user.id}")

    def process_giveaway_channels(message):
        try:
            user_states[message.chat.id]['channels'] = message.text
            msg = bot.send_message(message.chat.id, "Сколько будет победителей?")
            bot.register_next_step_handler(msg, process_giveaway_winners)
        except Exception as e:
            log_error(bot.logger, e, f"обработка каналов розыгрыша от пользователя {message.from_user.id}")

    def process_giveaway_winners(message):
        try:
            if not message.text.isdigit():
                msg = bot.send_message(message.chat.id, "Введите число победителей:")
                bot.register_next_step_handler(msg, process_giveaway_winners)
                return
            user_states[message.chat.id]['winners_count'] = int(message.text)
            msg = bot.send_message(message.chat.id, "Укажите дату и время окончания (например, 2024-08-01 18:00)")
            bot.register_next_step_handler(msg, process_giveaway_endtime)
        except Exception as e:
            log_error(bot.logger, e, f"обработка количества победителей от пользователя {message.from_user.id}")

    def process_giveaway_endtime(message):
        try:
            user_states[message.chat.id]['end_datetime'] = message.text  # Здесь можно добавить парсинг и валидацию
            msg = bot.send_message(message.chat.id, "Введите текст кнопки участия (по умолчанию 'Участвовать') или напишите 'по умолчанию'")
            bot.register_next_step_handler(msg, process_giveaway_button)
        except Exception as e:
            log_error(bot.logger, e, f"обработка времени окончания розыгрыша от пользователя {message.from_user.id}")

    def process_giveaway_button(message):
        try:
            button_text = message.text if message.text.lower() != 'по умолчанию' else 'Участвовать'
            user_states[message.chat.id]['button_text'] = button_text
            session = SessionLocal()
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                user = User(telegram_id=str(message.from_user.id), username=message.from_user.username)
                session.add(user)
                session.commit()
                log_info(bot.logger, f"Создан новый пользователь: {message.from_user.username} (ID: {message.from_user.id})")
            
            giveaway = Giveaway(
                creator_id=user.id,
                description=user_states[message.chat.id]['description'],
                prize=user_states[message.chat.id]['description'],
                winners_count=user_states[message.chat.id]['winners_count'],
                end_datetime=user_states[message.chat.id]['end_datetime'],
                join_button_text=user_states[message.chat.id]['button_text']
            )
            session.add(giveaway)
            session.commit()
            session.close()
            log_info(bot.logger, f"Создан новый розыгрыш пользователем {message.from_user.username} (ID: {message.from_user.id})")
            bot.send_message(message.chat.id, "Розыгрыш успешно создан!")
            user_states.pop(message.chat.id, None)
        except Exception as e:
            log_error(bot.logger, e, f"создание розыгрыша пользователем {message.from_user.id}")

    # === Просмотр розыгрышей ===
    @bot.message_handler(commands=['my_giveaways'])
    def my_giveaways_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'my_giveaways')
            session = SessionLocal()
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                bot.send_message(message.chat.id, 'У вас нет созданных розыгрышей.')
                session.close()
                return
            giveaways = session.query(Giveaway).filter_by(creator_id=user.id).all()
            if not giveaways:
                bot.send_message(message.chat.id, 'У вас нет созданных розыгрышей.')
            else:
                text = '\n'.join([f"{g.id}: {g.description or 'Без описания'}" for g in giveaways])
                bot.send_message(message.chat.id, f'Ваши розыгрыши:\n{text}')
            session.close()
        except Exception as e:
            log_error(bot.logger, e, f"просмотр розыгрышей пользователем {message.from_user.id}")

    # === Добавление канала ===
    @bot.message_handler(commands=['add_channel'])
    def add_channel_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'add_channel')
            msg = bot.send_message(message.chat.id, "Пришлите ссылку на канал или группу, где вы администратор:")
            bot.register_next_step_handler(msg, process_add_channel)
        except Exception as e:
            log_error(bot.logger, e, f"обработка команды /add_channel от пользователя {message.from_user.id}")

    def process_add_channel(message):
        try:
            link = message.text
            session = SessionLocal()
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                user = User(telegram_id=str(message.from_user.id), username=message.from_user.username)
                session.add(user)
                session.commit()
                log_info(bot.logger, f"Создан новый пользователь: {message.from_user.username} (ID: {message.from_user.id})")
            
            channel = Channel(telegram_id=link, title=link, owner_id=user.id)
            session.add(channel)
            session.commit()
            session.close()
            log_info(bot.logger, f"Добавлен новый канал пользователем {message.from_user.username} (ID: {message.from_user.id}): {link}")
            bot.send_message(message.chat.id, "Канал успешно добавлен!")
        except Exception as e:
            log_error(bot.logger, e, f"добавление канала пользователем {message.from_user.id}")

    # === Просмотр каналов ===
    @bot.message_handler(commands=['my_channels'])
    def my_channels_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'my_channels')
            session = SessionLocal()
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                bot.send_message(message.chat.id, 'У вас нет добавленных каналов.')
                session.close()
                return
            channels = session.query(Channel).filter_by(owner_id=user.id).all()
            if not channels:
                bot.send_message(message.chat.id, 'У вас нет добавленных каналов.')
            else:
                text = '\n'.join([f"{c.id}: {c.title or c.telegram_id}" for c in channels])
                bot.send_message(message.chat.id, f'Ваши каналы:\n{text}')
            session.close()
        except Exception as e:
            log_error(bot.logger, e, f"просмотр каналов пользователем {message.from_user.id}")

    # === Поддержка ===
    @bot.message_handler(commands=['support'])
    def support_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'support')
            msg = bot.send_message(message.chat.id, "Опишите вашу проблему или вопрос:")
            bot.register_next_step_handler(msg, process_support_message)
        except Exception as e:
            log_error(bot.logger, e, f"обработка команды /support от пользователя {message.from_user.id}")

    def process_support_message(message):
        try:
            session = SessionLocal()
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                user = User(telegram_id=str(message.from_user.id), username=message.from_user.username)
                session.add(user)
                session.commit()
                log_info(bot.logger, f"Создан новый пользователь: {message.from_user.username} (ID: {message.from_user.id})")
            
            support = SupportRequest(user_id=user.id, message=message.text)
            session.add(support)
            session.commit()
            session.close()
            log_info(bot.logger, f"Отправлено сообщение в поддержку от пользователя {message.from_user.username} (ID: {message.from_user.id})")
            bot.send_message(message.chat.id, "Ваше сообщение отправлено в поддержку!")
        except Exception as e:
            log_error(bot.logger, e, f"отправка сообщения в поддержку пользователем {message.from_user.id}") 