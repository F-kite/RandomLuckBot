import asyncio
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from models import User, Channel, Giveaway, GiveawayChannel, GiveawayParticipant, SupportRequest
from db import SessionLocal
from utils import log_command, log_error, log_info
from message_utils import message_manager

user_states = {}  # Для хранения промежуточных данных по chat_id

def register_handlers(bot: AsyncTeleBot):
    @bot.message_handler(commands=['start'])
    async def start_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'start')
            
            # Создаем Reply-кнопки
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add(
                types.KeyboardButton("🎁 Создать розыгрыш"),
                types.KeyboardButton("📋 Мои розыгрыши"),
                types.KeyboardButton("📺 Мои каналы"),
                types.KeyboardButton("🆘 Техническая поддержка")
            )
            
            await bot.send_message(
                message.chat.id, 
                message_manager.get_message('welcome', 'start'),
                reply_markup=markup
            )
        except Exception as e:
            log_error(bot.logger, e, f"обработка команды /start от пользователя {message.from_user.id}")

    @bot.message_handler(commands=['help'])
    async def help_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'help')
            await bot.send_message(
                message.chat.id,
                message_manager.get_message('help', 'commands')
            )
        except Exception as e:
            log_error(bot.logger, e, f"обработка команды /help от пользователя {message.from_user.id}")

    # === Обработчики Reply-кнопок ===
    @bot.message_handler(func=lambda message: message.text == "🎁 Создать розыгрыш" or message.text == '/new_giveaway')
    async def create_giveaway_button_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'create_giveaway_button')
            user_states[message.chat.id] = {'state': 'waiting_media'}
            await bot.send_message(message.chat.id, message_manager.get_message('giveaway', 'create', 'request_media'))
        except Exception as e:
            log_error(bot.logger, e, f"обработка кнопки 'Создать розыгрыш' от пользователя {message.from_user.id}")

    @bot.message_handler(func=lambda message: message.text == "📋 Мои розыгрыши" or message.text == '/my_giveaways')
    async def my_giveaways_button_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'my_giveaways_button')
            session = SessionLocal()
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await bot.send_message(message.chat.id, message_manager.get_message('giveaway', 'list', 'no_giveaways'))
                session.close()
                return
            giveaways = session.query(Giveaway).filter_by(creator_id=user.id).all()
            if not giveaways:
                await bot.send_message(message.chat.id, message_manager.get_message('giveaway', 'list', 'no_giveaways'))
            else:
                text = '\n'.join([f"{g.id}: {g.description or 'Без описания'}" for g in giveaways])
                await bot.send_message(message.chat.id, message_manager.get_message('giveaway', 'list', 'giveaways_list', text=text))
            session.close()
        except Exception as e:
            log_error(bot.logger, e, f"обработка кнопки 'Мои розыгрыши' от пользователя {message.from_user.id}")

    @bot.message_handler(func=lambda message: message.text == "📺 Мои каналы" or message.text == '/my_channels')
    async def my_channels_button_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'my_channels_button')
            session = SessionLocal()
            user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
            if not user:
                await bot.send_message(message.chat.id, message_manager.get_message('channel', 'list', 'no_channels'))
                session.close()
                return
            channels = session.query(Channel).filter_by(owner_id=user.id).all()
            if not channels:
                await bot.send_message(message.chat.id, message_manager.get_message('channel', 'list', 'no_channels'))
            else:
                text = '\n'.join([f"{c.id}: {c.title or c.telegram_id}" for c in channels])
                await bot.send_message(message.chat.id, message_manager.get_message('channel', 'list', 'channels_list', text=text))
            
            # Добавляем inline-кнопку для добавления канала
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                message_manager.get_message('channel', 'list', 'add_button'),
                callback_data="add_channel"
            ))
            await bot.send_message(
                message.chat.id, 
                "Выберите действие:",
                reply_markup=markup
            )
            session.close()
        except Exception as e:
            log_error(bot.logger, e, f"обработка кнопки 'Мои каналы' от пользователя {message.from_user.id}")

    @bot.message_handler(func=lambda message: message.text == "🆘 Техническая поддержка" or message.text == '/support')
    async def support_button_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'support_button')
            user_states[message.chat.id] = {'state': 'waiting_support_message'}
            await bot.send_message(message.chat.id, message_manager.get_message('support', 'request_message'))
        except Exception as e:
            log_error(bot.logger, e, f"обработка кнопки 'Техническая поддержка' от пользователя {message.from_user.id}")

    # === Обработчик всех сообщений для состояний ===
    @bot.message_handler(func=lambda message: True)
    async def handle_all_messages(message):
        try:
            chat_id = message.chat.id
            user_state = user_states.get(chat_id, {})
            current_state = user_state.get('state')

            if not current_state:
                return  # Если нет активного состояния, игнорируем сообщение

            if current_state == 'waiting_media':
                # Обработка медиа для розыгрыша
                user_states[chat_id]['media'] = getattr(message, 'photo', None) or getattr(message, 'video', None) or getattr(message, 'animation', None)
                user_states[chat_id]['state'] = 'waiting_description'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_description'))

            elif current_state == 'waiting_description':
                # Обработка описания розыгрыша
                user_states[chat_id]['description'] = message.text
                user_states[chat_id]['state'] = 'waiting_channels'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_channels'))

            elif current_state == 'waiting_channels':
                # Обработка каналов розыгрыша
                user_states[chat_id]['channels'] = message.text
                user_states[chat_id]['state'] = 'waiting_winners'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_winners'))

            elif current_state == 'waiting_winners':
                # Обработка количества победителей
                if not message.text.isdigit():
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_winners'))
                    return
                user_states[chat_id]['winners_count'] = int(message.text)
                user_states[chat_id]['state'] = 'waiting_endtime'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_endtime'))

            elif current_state == 'waiting_endtime':
                # Обработка времени окончания
                user_states[chat_id]['end_datetime'] = message.text
                user_states[chat_id]['state'] = 'waiting_button'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_button'))

            elif current_state == 'waiting_button':
                # Обработка текста кнопки и создание розыгрыша
                button_text = message.text if message.text.lower() != 'по умолчанию' else 'Участвовать'
                user_states[chat_id]['button_text'] = button_text
                
                # Создание розыгрыша
                session = SessionLocal()
                try:
                    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
                    if not user:
                        user = User(telegram_id=str(message.from_user.id), username=message.from_user.username)
                        session.add(user)
                        session.commit()
                        log_info(bot.logger, f"Создан новый пользователь: {message.from_user.username} (ID: {message.from_user.id})")
                    
                    giveaway = Giveaway(
                        creator_id=user.id,
                        description=user_states[chat_id]['description'],
                        prize=user_states[chat_id]['description'],
                        winners_count=user_states[chat_id]['winners_count'],
                        end_datetime=user_states[chat_id]['end_datetime'],
                        join_button_text=user_states[chat_id]['button_text']
                    )
                    session.add(giveaway)
                    session.commit()
                    log_info(bot.logger, f"Создан новый розыгрыш пользователем {message.from_user.username} (ID: {message.from_user.id})")
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'success'))
                except Exception as e:
                    log_error(bot.logger, e, f"создание розыгрыша пользователем {message.from_user.id}")
                finally:
                    session.close()
                    user_states.pop(chat_id, None)

            elif current_state == 'waiting_support_message':
                # Обработка сообщения в поддержку
                session = SessionLocal()
                try:
                    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
                    if not user:
                        user = User(telegram_id=str(message.from_user.id), username=message.from_user.username)
                        session.add(user)
                        session.commit()
                        log_info(bot.logger, f"Создан новый пользователь: {message.from_user.username} (ID: {message.from_user.id})")
                    
                    support = SupportRequest(user_id=user.id, message=message.text)
                    session.add(support)
                    session.commit()
                    log_info(bot.logger, f"Отправлено сообщение в поддержку от пользователя {message.from_user.username} (ID: {message.from_user.id})")
                    await bot.send_message(chat_id, message_manager.get_message('support', 'success'))
                except Exception as e:
                    log_error(bot.logger, e, f"отправка сообщения в поддержку пользователем {message.from_user.id}")
                finally:
                    session.close()
                    user_states.pop(chat_id, None)

            elif current_state == 'waiting_channel_link':
                # Обработка добавления канала
                link = message.text
                session = SessionLocal()
                try:
                    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
                    if not user:
                        user = User(telegram_id=str(message.from_user.id), username=message.from_user.username)
                        session.add(user)
                        session.commit()
                        log_info(bot.logger, f"Создан новый пользователь: {message.from_user.username} (ID: {message.from_user.id})")
                    
                    channel = Channel(telegram_id=link, title=link, owner_id=user.id)
                    session.add(channel)
                    session.commit()
                    log_info(bot.logger, f"Добавлен новый канал пользователем {message.from_user.username} (ID: {message.from_user.id}): {link}")
                    await bot.send_message(chat_id, message_manager.get_message('channel', 'add', 'success'))
                except Exception as e:
                    log_error(bot.logger, e, f"добавление канала пользователем {message.from_user.id}")
                finally:
                    session.close()
                    user_states.pop(chat_id, None)

        except Exception as e:
            log_error(bot.logger, e, f"обработка сообщения от пользователя {message.from_user.id}")





    # === Обработчики inline-кнопок ===
    @bot.callback_query_handler(func=lambda call: call.data == "add_channel")
    async def add_channel_callback_handler(call):
        try:
            log_command(bot.logger, call.from_user.id, call.from_user.username, 'add_channel_callback')
            await bot.answer_callback_query(call.id)
            user_states[call.message.chat.id] = {'state': 'waiting_channel_link'}
            await bot.send_message(call.message.chat.id, message_manager.get_message('channel', 'add', 'request_link'))
        except Exception as e:
            log_error(bot.logger, e, f"обработка callback 'add_channel' от пользователя {call.from_user.id}")