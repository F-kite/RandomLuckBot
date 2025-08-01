import telebot
import pytz
from datetime import datetime
from sqlalchemy import and_
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from models import User, Channel, Giveaway, GiveawayChannel, GiveawayParticipant, SupportRequest
from db import SessionLocal
from utils import log_command, log_error, log_info
from message_utils import message_manager

user_states = {}  # Для хранения промежуточных данных по chat_id

def get_main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    """Создает и возвращает клавиатуру главного меню."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🎁 Создать розыгрыш"),
        types.KeyboardButton("📋 Мои розыгрыши"),
        types.KeyboardButton("📺 Мои каналы"),
        types.KeyboardButton("🆘 Техническая поддержка")
    )
    return markup

# --- Вспомогательные функции для валидации ---

def parse_datetime(dt_str: str, logger) -> datetime:
    """Парсит строку даты/времени в формате ДД.ММ.ГГГГ ЧЧ:ММ, интерпретируя её как Московское время."""
    try:
        # 1. Определяем московский часовой пояс
        moscow_tz = pytz.timezone('Europe/Moscow')
        
        # 2. Парсим строку как "наивный" (без информации о часовом поясе) datetime
        naive_dt = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
        
        # 3. Присваиваем московский часовой пояс разобранному времени
        #    localize() - правильный способ для "наивного" datetime
        moscow_dt = moscow_tz.localize(naive_dt)
        
        # 4. Конвертируем в UTC для хранения в БД (если ваша БД хранит время в UTC)
        #    Это обеспечивает согласованность, если сервер когда-либо сменит часовой пояс.
        utc_dt = moscow_dt.astimezone(pytz.utc)
        
        # 5. Для сравнения с "сейчас" внутри бота (который использует datetime.now())
        #    нужно привести "сейчас" к тому же часовому поясу или UTC.
        #    Проще всего хранить всё в UTC.
        
        # Возвращаем время в UTC для хранения в БД
        return utc_dt
        
    except ValueError as e:
        log_error(logger, e, f"Парсинг даты/времени '{dt_str}'")
        return None

def validate_channel_links(text: str) -> list:
    """Проверяет и парсит список ссылок/юзернеймов каналов. Возвращает список кортежей (тип, значение) или None при ошибке."""
    if text.strip().lower() in ['нет', '']:
        return []
    
    links = [link.strip() for link in text.split(',')]
    validated_links = []
    for link in links:
        if not link:
            continue
        # Проверка @username
        if link.startswith('@') and len(link) > 1:
            validated_links.append(('username', link[1:])) # Сохраняем без @
        # Проверка ссылки t.me
        elif link.startswith('https://t.me/'):
            username_or_id = link.split('/')[-1]
            if username_or_id:
                validated_links.append(('link', username_or_id))
            else:
                 return None # Некорректная ссылка
        else:
            return None # Неизвестный формат
    return validated_links

async def create_giveaway_final(chat_id, message, bot):
    """Финальная функция создания розыгрыша в БД"""
    session = SessionLocal()
    try:
        # 1. Получаем или создаем пользователя
        user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
        if not user:
            user = User(telegram_id=str(message.from_user.id), username=message.from_user.username, first_name=message.from_user.first_name, last_name=message.from_user.last_name)
            session.add(user)
            session.flush() # Чтобы получить user.id

        # 2. Создаем объект Giveaway
        giveaway_data = user_states[chat_id]
        giveaway = Giveaway(
            creator_id=user.id,
            channel_id=giveaway_data['main_channel_id'],
            description=giveaway_data['description'],
            prize=giveaway_data['prize'],
            media_type=giveaway_data.get('media_type', 'none'),
            media_file_id=giveaway_data.get('media_file_id'),
            participation_button_text=giveaway_data['participation_button_text'],
            winners_count=giveaway_data['winners_count'],
            publication_time=giveaway_data['publication_time'],
            end_condition_type=giveaway_data['end_condition_type'],
            end_time=giveaway_data.get('end_time'),
            end_participants_count=giveaway_data.get('end_participants_count'),
            has_captcha=giveaway_data['has_captcha'],
            boost_enabled=giveaway_data['boost_enabled'],
            status='pending' # Или 'active', если публикуется сразу
        )
        session.add(giveaway)
        session.flush() # Чтобы получить giveaway.id

        # 3. Создаем связи с каналами (GiveawayChannel)
        # Основной канал всегда первый
        main_giveaway_channel = GiveawayChannel(giveaway_id=giveaway.id, channel_id=giveaway_data['main_channel_id'])
        session.add(main_giveaway_channel)

        # Дополнительные каналы
        for chan_type, chan_value in giveaway_data.get('required_channels_list', []):
            # Нужно найти или создать Channel в БД по username/link
            # Это упрощенный вариант. В реальном приложении лучше иметь отдельный механизм
            # синхронизации каналов или более сложную логику.
            # Для примера, предположим, что если канал не найден, мы его создаем как "внешний"
            # или пропускаем. Лучше всего - проверять, добавлен ли он пользователем.
            # Пока просто добавим запись, предполагая, что channel_id нужно как-то получить.
            # Это сложный момент, требующий доработки логики добавления каналов.
            # Для MVP можно хранить юзернеймы в JSON поле в Giveaway или создавать "внешние" записи.
            
            # ВРЕМЕННОЕ РЕШЕНИЕ: Сохраняем юзернеймы в JSON поле в Giveaway (если добавили в модель)
            # Или создаем "заглушку" в channels таблице.
            # Лучше: пересмотреть модель или логику.
            # Пока пропустим создание дополнительных GiveawayChannel для внешних каналов.
            # Они будут проверяться при участии другим способом (например, через API Telegram напрямую).
            
            # Если канал уже добавлен пользователем, создаем связь
            # (Это требует доработки логики добавления каналов, чтобы она сохраняла username)
            # Для демонстрации предположим, что мы можем найти по username
            if chan_type == 'username':
                existing_channel = session.query(Channel).filter_by(username=chan_value).first()
                if existing_channel and existing_channel.owner_id == user.id:
                     assoc = GiveawayChannel(giveaway_id=giveaway.id, channel_id=existing_channel.id)
                     session.add(assoc)
                # Если не найден, можно либо пропустить, либо создать "внешний" канал
                # (требует изменения модели или логики)
                # Пока просто логируем
                else:
                     log_info(bot.logger, f"Канал @{chan_value} не найден среди добавленных пользователем {user.id} или не принадлежит ему. Пропущен при создании розыгрыша {giveaway.id}.")

        session.commit()
        log_info(bot.logger, f"Создан новый розыгрыш ID {giveaway.id} пользователем {message.from_user.username} (ID: {message.from_user.id})")

        # 4. Отправляем сообщение об успехе
        await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'success'), reply_markup=get_main_menu_keyboard())
        
        # 5. Здесь можно запланировать задачи (публикация, завершение)
        # Это будет реализовано в разделе фоновых задач
        
    except Exception as e:
        session.rollback()
        log_error(bot.logger, e, f"создание розыгрыша пользователем {message.from_user.id}")
        await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'error'), reply_markup=get_main_menu_keyboard())
    finally:
        session.close()
        user_states.pop(chat_id, None)


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
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            message_template = message_manager.get_message('giveaway', 'create', 'request_media')
            final_message_text = message_template.format(bot_username=bot_username)
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'create_giveaway_button')
            user_states[message.chat.id] = {'state': 'waiting_media'}
            await bot.send_message(message.chat.id, final_message_text, parse_mode='HTML')
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
            
            # Создаем клавиатуру один раз
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                message_manager.get_message('channel', 'list', 'add_button'), # Убедитесь, что ключ 'add_button' есть в messages.json
                callback_data="add_channel"
            ))
            
            if not user:
                # Отправляем сообщение "нет каналов" с кнопкой
                await bot.send_message(
                    message.chat.id, 
                    message_manager.get_message('channel', 'list', 'no_channels'),
                    reply_markup=markup # Прикрепляем кнопку сюда
                )
                session.close()
                return
                
            channels = session.query(Channel).filter_by(owner_id=user.id).all()
            if not channels:
                # Отправляем сообщение "нет каналов" с кнопкой
                await bot.send_message(
                    message.chat.id, 
                    message_manager.get_message('channel', 'list', 'no_channels'),
                    reply_markup=markup # Прикрепляем кнопку сюда
                )
            else:
                # Формируем текст списка каналов
                # Используем username, если есть, иначе title, иначе telegram_id
                channel_lines = []
                for c in channels:
                    if c.username:
                        display_name = f"@{c.username}"
                    elif c.title:
                        display_name = c.title
                    else:
                        display_name = c.telegram_id if c.telegram_id else f"ID: {c.id}"
                    channel_lines.append(f"{c.id}: {display_name}")
                
                text = '\n'.join(channel_lines)
                
                # Отправляем список каналов с кнопкой
                await bot.send_message(
                    message.chat.id, 
                    message_manager.get_message('channel', 'list', 'channels_list', text=text),
                    reply_markup=markup # Прикрепляем кнопку сюда
                )
                
            session.close()
        except Exception as e:
            log_error(bot.logger, e, f"обработка кнопки 'Мои каналы' от пользователя {message.from_user.id}")
            # Можно отправить сообщение об ошибке, но без клавиатуры или с ней - как решите
            # await bot.send_message(message.chat.id, "❌ Произошла ошибка при загрузке списка каналов.", reply_markup=get_main_menu_keyboard()) 

    @bot.message_handler(func=lambda message: message.text == "🆘 Техническая поддержка" or message.text == '/support')
    async def support_button_handler(message):
        try:
            log_command(bot.logger, message.from_user.id, message.from_user.username, 'support_button')
            user_states[message.chat.id] = {'state': 'waiting_support_message'}
            await bot.send_message(message.chat.id, message_manager.get_message('support', 'request_message'))
        except Exception as e:
            log_error(bot.logger, e, f"обработка кнопки 'Техническая поддержка' от пользователя {message.from_user.id}")

    # === Обработчики inline-кнопок ===
    @bot.callback_query_handler(func=lambda call: call.data == "add_channel")
    async def add_channel_callback_handler(call):
        """Обработчик нажатия inline-кнопки 'Добавить канал'"""
        try:
            log_command(bot.logger, call.from_user.id, call.from_user.username, 'add_channel_callback')
            await bot.answer_callback_query(call.id) # Подтверждаем получение callback'а
            
            # Устанавливаем состояние ожидания ссылки/сообщения
            user_states[call.message.chat.id] = {'state': 'waiting_channel_input'}
            await bot.send_message(
                call.message.chat.id, 
                message_manager.get_message('channel', 'add', 'request_link'),
                reply_markup=types.ReplyKeyboardRemove() # Убираем reply-кнопки на время ввода
            )
        except Exception as e:
            log_error(bot.logger, e, f"обработка callback 'add_channel' от пользователя {call.from_user.id}")

    # === Обработчик всех сообщений для состояний ===
    @bot.my_chat_member_handler()
    async def my_chat_member_handler(chat_member_updated: types.ChatMemberUpdated):
        """
        Обработчик изменений статуса бота в чатах (каналах/группах).
        Используется для автоматического добавления каналов, куда бота пригласили,
        и уведомления пользователей об этом.
        """
        try:
            # Логируем информацию об апдейте для отладки
            log_info(
                bot.logger, 
                f"Апдейт my_chat_member: Бот {chat_member_updated.new_chat_member.user.id} "
                f"в чате {chat_member_updated.chat.id} ({chat_member_updated.chat.title}). "
                f"Старый статус: {chat_member_updated.old_chat_member.status}, "
                f"Новый статус: {chat_member_updated.new_chat_member.status}"
            )
            
            bot_user_id = (await bot.get_me()).id
            
            # Проверяем, что это апдейт о нашем боте
            if chat_member_updated.new_chat_member.user.id != bot_user_id:
                return # Апдейт не о нас, игнорируем

            chat = chat_member_updated.chat
            new_status = chat_member_updated.new_chat_member.status
            old_status = chat_member_updated.old_chat_member.status
            # Пользователь, который совершил действие (пригласил, назначил админом, удалил и т.д.)
            from_user = chat_member_updated.from_user 

            # --- Сценарий 1: Бот становится администратором ---
            if new_status == 'administrator' and old_status != 'administrator':
                log_info(
                    bot.logger, 
                    f"Бот приглашен и назначен администратором в {chat.type} '{chat.title}' (ID: {chat.id}) пользователем {from_user.username or from_user.id}"
                )
                
                # Проверяем, имеет ли бот право публиковать сообщения
                bot_member = chat_member_updated.new_chat_member
                # Для администратора в канале/группе Telegram API возвращает объект ChatMemberAdministrator
                # У него есть поле can_post_messages
                has_post_permission = getattr(bot_member, 'can_post_messages', False)
                
                if not has_post_permission:
                    log_info(bot.logger, f"Бот не имеет права публиковать сообщения в {chat.title} (ID: {chat.id})")
                    # Можно попытаться уведомить пользователя, но бот не может публиковать,
                    # поэтому уведомление будет через личные сообщения (если получится)
                    # Уведомление об ошибке прав будет в блоке уведомления пользователя
                else:
                    log_info(bot.logger, f"Бот имеет право публиковать сообщения в {chat.title} (ID: {chat.id})")

                # --- Автоматическое добавление канала и уведомление пользователя ---
                session = SessionLocal()
                try:
                    # 1. Получаем пользователя из БД по ID того, кто пригласил бота
                    user = session.query(User).filter_by(telegram_id=str(from_user.id)).first()
                    channel_added_to_db = False
                    notification_text = ""
                    
                    if user:
                        # 2. Проверяем, существует ли канал уже у этого пользователя
                        existing_channel = session.query(Channel).filter_by(telegram_id=str(chat.id), owner_id=user.id).first()
                        if not existing_channel:
                            # 3. Создаем запись о канале, если его нет
                            new_channel = Channel(
                                owner_id=user.id,
                                telegram_id=str(chat.id),
                                username=chat.username, # Может быть None для приватных каналов
                                title=chat.title,
                                is_public=(chat.username is not None),
                                # invite_link=... # Обычно бот не может получить invite link, только создать
                            )
                            session.add(new_channel)
                            session.commit() # Коммитим, чтобы убедиться, что всё сохранилось
                            channel_added_to_db = True
                            log_info(
                                bot.logger, 
                                f"Канал {chat.title} (@{chat.username or chat.id}) автоматически добавлен пользователю {from_user.username or from_user.id} в БД"
                            )
                            if has_post_permission:
                                notification_text = f"✅ Бот был успешно добавлен в {chat.type} '{chat.title}' (@{chat.username or chat.id}) и теперь может проводить там розыгрыши!"
                            else:
                                notification_text = (f"⚠️ Бот был добавлен в {chat.type} '{chat.title}' (@{chat.username or chat.id}), "
                                                    f"но ему не хватает права на публикацию сообщений. "
                                                    f"Пожалуйста, предоставьте боту право 'Публиковать сообщения' в настройках администратора канала.")
                        else:
                            log_info(bot.logger, f"Канал {chat.title} (ID: {chat.id}) уже есть у пользователя {from_user.username or from_user.id} в БД")
                            if has_post_permission:
                                notification_text = f"ℹ️ Бот уже имеет доступ к {chat.type} '{chat.title}' (@{chat.username or chat.id}) и может проводить там розыгрыши."
                            else:
                                notification_text = (f"⚠️ Бот уже добавлен в {chat.type} '{chat.title}' (@{chat.username or chat.id}), "
                                                    f"но ему не хватает права на публикацию сообщений. "
                                                    f"Пожалуйста, предоставьте боту право 'Публиковать сообщения' в настройках администратора канала.")

                        # --- Отправка уведомления пользователю в личные сообщения ---
                        try:
                            # from_user.id используется как chat_id для отправки личного сообщения
                            await bot.send_message(from_user.id, notification_text)
                            log_info(bot.logger, f"Уведомление об (добавлении/обновлении прав) отправлено пользователю {from_user.username or from_user.id}")
                        except telebot.apihelper.ApiException as e:
                            # Это может произойти, если пользователь заблокировал бота или никогда с ним не взаимодействовал
                            if "Forbidden" in str(e) or "bot can't initiate conversation" in str(e):
                                log_info(bot.logger, f"Не удалось отправить уведомление пользователю {from_user.username or from_user.id}: пользователь не начал чат с ботом или заблокировал его.")
                            else:
                                log_error(bot.logger, e, f"отправка уведомления пользователю {from_user.username or from_user.id} об (добавлении/обновлении прав) канала")
                        except Exception as e:
                            log_error(bot.logger, e, f"неожиданная ошибка при отправке уведомления пользователю {from_user.username or from_user.id} об (добавлении/обновлении прав) канала")
                        # --- Конец отправки уведомления ---
                    else:
                        # Пользователь не найден в БД. 
                        log_info(bot.logger, f"Пользователь {from_user.username or from_user.id}, пригласивший бота, не найден в БД. Канал не будет автоматически связан до первого обращения пользователя к боту.")
                        # Можно попытаться отправить сообщение, но это вряд ли сработает
                        # Лучше дождаться, пока пользователь сам напишет боту.
                        
                except Exception as e:
                    session.rollback()
                    log_error(bot.logger, e, f"автоматическое добавление/уведомление для канала {chat.id} и пользователя {from_user.id}")
                finally:
                    session.close()

            # --- Сценарий 2: Бота удалили или заблокировали ---
            elif new_status in ['left', 'kicked'] and old_status in ['administrator', 'member', 'restricted']:
                log_info(
                    bot.logger, 
                    f"Бот удален или заблокирован в {chat.type} '{chat.title}' (ID: {chat.id})"
                    # f" пользователем/администратором {from_user.username or from_user.id}" 
                    # from_user может быть недоступен или не тем, кто удалил, если бота удалили через настройки канала
                )
                
                # Определяем инициатора. Если статус from_user.id == bot_user_id, значит, бот сам вышел или его удалил админ.
                # Точную информацию трудно получить. Проще искать владельца канала в БД.
                session = SessionLocal()
                try:
                    # Ищем всех пользователей, у которых есть этот канал в списке
                    affected_users = session.query(User).join(Channel).filter(Channel.telegram_id == str(chat.id)).all()
                    
                    if affected_users:
                        for user in affected_users:
                            # Отправляем уведомление каждому владельцу
                            notification_text = f"⚠️ Бот был удален или заблокирован в {chat.type} '{chat.title}' (@{chat.username or chat.id}). Вы больше не можете проводить в нем розыгрыши через этого бота. Если это ошибка, добавьте бота обратно и назначьте администратором с правом публиковать сообщения."
                            try:
                                await bot.send_message(user.telegram_id, notification_text) # user.telegram_id это строка
                                log_info(bot.logger, f"Уведомление об удалении/блокировке отправлено пользователю {user.username or user.telegram_id}")
                            except telebot.apihelper.ApiException as e:
                                if "Forbidden" in str(e) or "bot can't initiate conversation" in str(e):
                                    log_info(bot.logger, f"Не удалось отправить уведомление об удалении пользователю {user.username or user.telegram_id}: пользователь не начал чат с ботом или заблокировал его.")
                                else:
                                    log_error(bot.logger, e, f"отправка уведомления пользователю {user.username or user.telegram_id} об удалении/блокировке канала")
                            except Exception as e:
                                log_error(bot.logger, e, f"неожиданная ошибка при отправке уведомления пользователю {user.username or user.telegram_id} об удалении/блокировке канала")
                            
                            # (Опционально) Можно пометить канал как неактивный или удалить
                            channels_to_update = session.query(Channel).filter_by(telegram_id=str(chat.id), owner_id=user.id).all()
                            for ch in channels_to_update:
                                session.delete(ch) # Удаление
                            session.commit()
                            
                    else:
                        log_info(bot.logger, f"Канал {chat.title} (ID: {chat.id}) не найден ни у одного пользователя в БД при удалении бота.")
                        
                except Exception as e:
                    log_error(bot.logger, e, f"обработка удаления/блокировки бота в канале {chat.id}")
                finally:
                    session.close()
                    
            # --- Сценарий 3: Боту изменили права (например, убрали can_post_messages) ---
            elif new_status == 'administrator' and old_status == 'administrator':
                # Сравниваем конкретные права, если они важны
                # old_member = chat_member_updated.old_chat_member
                # new_member = chat_member_updated.new_chat_member
                # Например, если раньше было can_post_messages=True, а теперь False
                # Это более сложный сценарий, можно реализовать позже при необходимости.
                log_info(bot.logger, f"Права бота в {chat.type} '{chat.title}' (ID: {chat.id}) были изменены.")
                
        except Exception as e:
            log_error(bot.logger, e, "обработка my_chat_member апдейта")
    
    @bot.message_handler(content_types=[
        'text', 'photo', 'video', 'animation', 'document', 
    ])
    async def handle_all_messages(message):
        try:
            chat_id = message.chat.id
            user_state = user_states.get(chat_id, {})
            current_state = user_state.get('state')

            if not current_state:
                return # Если нет активного состояния, игнорируем сообщение

            # --- Шаг 1: Медиа или Пропуск ---
            if current_state == 'waiting_media':
                try:
                    # Проверяем, является ли сообщение медиа
                    photo = getattr(message, 'photo', None)
                    video = getattr(message, 'video', None)
                    animation = getattr(message, 'animation', None) # Проверяем animation отдельно
                    document = getattr(message, 'document', None)

                    if photo:
                        log_info(bot.logger, f"Обнаружено фото, количество размеров: {len(photo)}")
                        user_states[chat_id]['media_type'] = 'photo'
                        # Берем фото с наибольшим разрешением
                        user_states[chat_id]['media_file_id'] = photo[-1].file_id
                        await bot.send_message(chat_id, "✅ Фото получено.")
                    elif video:
                        log_info(bot.logger, f"Обнаружено видео, file_id: {video.file_id}")
                        user_states[chat_id]['media_type'] = 'video'
                        user_states[chat_id]['media_file_id'] = video.file_id
                        await bot.send_message(chat_id, "✅ Видео получено.")
                    elif animation:
                        log_info(bot.logger, f"Обнаружено анимация, file_id: {animation.file_id}")
                        user_states[chat_id]['media_type'] = 'animation'
                        user_states[chat_id]['media_file_id'] = animation.file_id
                        await bot.send_message(chat_id, "✅ GIF (анимация) получена.")
                    elif document and document.mime_type:
                        if document.mime_type.startswith('image/'):
                            # Дополнительная проверка для изображений, отправленных как документы
                            log_info(bot.logger, f"Обнаружено изображение (документ), file_id: {document.file_id}")
                            user_states[chat_id]['media_type'] = 'document'
                            user_states[chat_id]['media_file_id'] = document.file_id
                            await bot.send_message(chat_id, "✅ Изображение (как документ) получено.")
                        else:
                            # Дополнительная проверка для изображений, отправленных как документы
                            log_info(bot.logger, f"Обнаружен документ, file_id: {document.file_id}")
                            await bot.send_message(chat_id, "❌ Документ не является изображением. Повторите попытку.")
                            user_states[chat_id]['state'] = 'waiting_media'
                            return
                    else:
                        # Если нет медиа, считаем, что пользователь пропустил этот шаг
                        log_info(bot.logger, f"Медиа не обнаружено. content_type: {message.content_type}")
                        user_states[chat_id]['media_type'] = 'none'
                        user_states[chat_id]['media_file_id'] = None
                        await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'media_skipped'))
                        # Не меняем состояние, просто переходим к следующему шагу
                    
                    user_states[chat_id]['state'] = 'waiting_description'
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_description'))

                except Exception as e:
                    log_error(bot.logger, e, f"обработка медиа в состоянии waiting_media от пользователя {message.from_user.id}")
                    await bot.send_message(chat_id, "❌ Произошла ошибка при обработке медиа. Попробуйте еще раз.")
                    user_states[chat_id]['state'] = 'waiting_media'

            # --- Шаг 2: Описание ---
            elif current_state == 'waiting_description':
                if not message.text or not message.text.strip():
                    await bot.send_message(chat_id, "❌ Описание не может быть пустым. Пожалуйста, введите описание розыгрыша.")
                    return
                user_states[chat_id]['description'] = message.text.strip()
                user_states[chat_id]['state'] = 'waiting_prize'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_prize'))

            # --- Шаг 3: Приз ---
            elif current_state == 'waiting_prize':
                if not message.text or not message.text.strip():
                    await bot.send_message(chat_id, "❌ Приз не может быть пустым. Пожалуйста, введите приз.")
                    return
                user_states[chat_id]['prize'] = message.text.strip()
                
                # --- Шаг 4: Выбор основного канала ---
                session = SessionLocal()
                try:
                    user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
                    if not user:
                        await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'no_channels_available'))
                        user_states.pop(chat_id, None)
                        return

                    channels = session.query(Channel).filter_by(owner_id=user.id).all()
                    if not channels:
                        await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'no_channels_available'))
                        user_states.pop(chat_id, None)
                        return

                    # Создаем клавиатуру с каналами
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                    for channel in channels:
                        # Отображаем юзернейм или title
                        display_name = f"@{channel.username}" if channel.username else channel.title or f"ID: {channel.telegram_id}"
                        markup.add(types.KeyboardButton(display_name))
                    # Добавляем кнопку "Отмена"
                    markup.add(types.KeyboardButton("❌ Отмена"))

                    user_states[chat_id]['available_channels'] = {ch.id: ch for ch in channels} # Сохраняем для проверки
                    user_states[chat_id]['state'] = 'waiting_main_channel'
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_main_channel'), reply_markup=markup)
                finally:
                    session.close()

            # --- Шаг 5: Основной канал ---
            elif current_state == 'waiting_main_channel':
                if message.text == "❌ Отмена":
                    await bot.send_message(chat_id, "❌ Создание розыгрыша отменено.", reply_markup=get_main_menu_keyboard())
                    user_states.pop(chat_id, None)
                    return

                selected_text = message.text.strip()
                channel_id_selected = None
                
                # Ищем ID канала по отображаемому имени
                for ch_id, ch_obj in user_states[chat_id].get('available_channels', {}).items():
                    display_name = f"@{ch_obj.username}" if ch_obj.username else ch_obj.title or f"ID: {ch_obj.telegram_id}"
                    if display_name == selected_text:
                        channel_id_selected = ch_id
                        break
                
                if not channel_id_selected:
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_channel_selection'))
                    # Клавиатура уже отправлена на предыдущем шаге, повторно не отправляем
                    return
                
                user_states[chat_id]['main_channel_id'] = channel_id_selected
                user_states[chat_id]['state'] = 'waiting_required_channels'
                # Отправляем сообщение с примером
                example_msg = "Пример: @channel1, https://t.me/channel2, @channel3\nИли напишите 'нет'"
                await bot.send_message(chat_id, f"{message_manager.get_message('giveaway', 'create', 'request_required_channels')}\n{example_msg}", reply_markup=types.ReplyKeyboardRemove())

            # --- Шаг 6: Дополнительные обязательные каналы ---
            elif current_state == 'waiting_required_channels':
                text = message.text.strip()
                if text.lower() == 'нет':
                    user_states[chat_id]['required_channels_list'] = []
                else:
                    validated_links = validate_channel_links(text)
                    if validated_links is None:
                        await bot.send_message(chat_id, f"{message_manager.get_message('giveaway', 'create', 'invalid_channel_format')}\nПример: @channel1, https://t.me/channel2, нет")
                        return
                    user_states[chat_id]['required_channels_list'] = validated_links # Список кортежей (тип, значение)

                user_states[chat_id]['state'] = 'waiting_winners'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_winners'))

            # --- Шаг 7: Количество победителей ---
            elif current_state == 'waiting_winners':
                if not message.text.isdigit() or int(message.text) <= 0:
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_winners'))
                    return
                user_states[chat_id]['winners_count'] = int(message.text)
                user_states[chat_id]['state'] = 'waiting_publication_time'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_publication_time'))

            # --- Шаг 8: Время публикации ---
            elif current_state == 'waiting_publication_time':
                text = message.text.strip().lower()
                now = datetime.now(pytz.utc) # или datetime.now(pytz.utc) если работаем в UTC
                if text == 'сейчас':
                    user_states[chat_id]['publication_time'] = now
                else:
                    pub_time = parse_datetime(text, bot.logger)
                    if not pub_time: # parse_datetime вернул None из-за ошибки
                        await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_publication_time'))
                        return
                    # pub_time теперь в UTC, now тоже в UTC - сравнение корректно
                    if pub_time < now: 
                        await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_publication_time'))
                        return
                    user_states[chat_id]['publication_time'] = pub_time
                
                # --- Шаг 9: Условие завершения ---
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.add(types.KeyboardButton("По времени"))
                markup.add(types.KeyboardButton("По количеству участников"))
                user_states[chat_id]['state'] = 'waiting_end_condition'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_end_condition'), reply_markup=markup)

            # --- Шаг 10: Выбор условия завершения ---
            elif current_state == 'waiting_end_condition':
                text = message.text.strip()
                if text == "По времени":
                    user_states[chat_id]['end_condition_type'] = 'time'
                    user_states[chat_id]['state'] = 'waiting_end_time'
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_end_time'), reply_markup=types.ReplyKeyboardRemove())
                elif text == "По количеству участников":
                    user_states[chat_id]['end_condition_type'] = 'participants'
                    user_states[chat_id]['state'] = 'waiting_end_participants'
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_end_participants'), reply_markup=types.ReplyKeyboardRemove())
                else:
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_end_condition'), reply_markup=markup) # Повторяем клавиатуру
                    return

            # --- Шаг 11a: Время завершения ---
            elif current_state == 'waiting_end_time':
                end_time = parse_datetime(message.text.strip(), bot.logger)
                if not end_time:
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_end_time'))
                    return
                
                pub_time = user_states[chat_id]['publication_time']
                now = datetime.now(pytz.utc)
                if end_time < now or end_time <= pub_time:
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_end_time'))
                    return

                user_states[chat_id]['end_time'] = end_time
                user_states[chat_id]['end_participants_count'] = None # Не используется
                # --- Шаг 12: Капча ---
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.add(types.KeyboardButton("Да"))
                markup.add(types.KeyboardButton("Нет"))
                user_states[chat_id]['state'] = 'waiting_captcha'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_captcha'), reply_markup=markup)

            # --- Шаг 11b: Количество участников для завершения ---
            elif current_state == 'waiting_end_participants':
                if not message.text.isdigit() or int(message.text) <= 0:
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_end_participants'))
                    return
                user_states[chat_id]['end_participants_count'] = int(message.text)
                user_states[chat_id]['end_time'] = None # Не используется
                # --- Шаг 12: Капча ---
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.add(types.KeyboardButton("Да"))
                markup.add(types.KeyboardButton("Нет"))
                user_states[chat_id]['state'] = 'waiting_captcha'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_captcha'), reply_markup=markup)

            # --- Шаг 13: Капча ---
            elif current_state == 'waiting_captcha':
                text = message.text.strip()
                if text == "Да":
                    user_states[chat_id]['has_captcha'] = True
                elif text == "Нет":
                    user_states[chat_id]['has_captcha'] = False
                else:
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                    markup.add(types.KeyboardButton("Да"))
                    markup.add(types.KeyboardButton("Нет"))
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_captcha'), reply_markup=markup)
                    return
                
                # --- Шаг 14: Бусты ---
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.add(types.KeyboardButton("Да"))
                markup.add(types.KeyboardButton("Нет"))
                user_states[chat_id]['state'] = 'waiting_boost'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_boost'), reply_markup=markup)

            # --- Шаг 15: Бусты ---
            elif current_state == 'waiting_boost':
                text = message.text.strip()
                if text == "Да":
                    user_states[chat_id]['boost_enabled'] = True
                elif text == "Нет":
                    user_states[chat_id]['boost_enabled'] = False
                else:
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                    markup.add(types.KeyboardButton("Да"))
                    markup.add(types.KeyboardButton("Нет"))
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_boost'), reply_markup=markup)
                    return

                user_states[chat_id]['state'] = 'waiting_button_text'
                await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'request_button_text'), reply_markup=types.ReplyKeyboardRemove())

            # --- Шаг 16: Текст кнопки ---
            elif current_state == 'waiting_button_text':
                text = message.text.strip()
                if not text:
                    await bot.send_message(chat_id, message_manager.get_message('giveaway', 'create', 'invalid_button_text'))
                    return
                if text.lower() == 'по умолчанию':
                    user_states[chat_id]['participation_button_text'] = 'Участвовать'
                else:
                    user_states[chat_id]['participation_button_text'] = text

                # --- Финальный шаг: Создание розыгрыша ---
                await create_giveaway_final(chat_id, message, bot)


            # --- Добавление канала ---
            elif current_state == 'waiting_channel_input':
                try:
                    session = SessionLocal()
                    # 1. Определяем telegram_id или username канала
                    channel_identifier = None # Это будет строка, уникально идентифицирующая канал
                    channel_type = None # 'username' или 'id'
                    
                    if message.forward_from_chat and message.forward_from_chat.type in ['channel', 'supergroup']:
                        # Пользователь переслал сообщение из канала
                        channel_identifier = str(message.forward_from_chat.id)
                        channel_type = 'id'
                        channel_title = message.forward_from_chat.title
                        channel_username = message.forward_from_chat.username # Может быть None
                    elif message.text and message.text.startswith('@'):
                        # Пользователь отправил @username
                        channel_identifier = message.text[1:] # Убираем @
                        channel_type = 'username'
                        channel_username = channel_identifier
                        channel_title = None # Заголовок получим позже через API
                    else:
                        await bot.send_message(
                            chat_id, 
                            message_manager.get_message('channel', 'add', 'invalid_input')
                        )
                        return # Остаемся в том же состоянии

                    if not channel_identifier:
                        await bot.send_message(
                            chat_id, 
                            message_manager.get_message('channel', 'add', 'invalid_input')
                        )
                        return

                    # 2. Проверяем, существует ли канал уже у этого пользователя
                    existing_channel = None
                    if channel_type == 'id':
                        existing_channel = session.query(Channel).filter_by(telegram_id=channel_identifier, owner_id=session.query(User.id).filter_by(telegram_id=str(message.from_user.id)).scalar()).first()
                    elif channel_type == 'username':
                        # Сначала ищем по username среди каналов пользователя
                        user_id_subq = session.query(User.id).filter_by(telegram_id=str(message.from_user.id)).scalar()
                        existing_channel = session.query(Channel).filter(Channel.username == channel_identifier, Channel.owner_id == user_id_subq).first()
                        # Если не нашли, можно попробовать получить ID через getChat и снова поискать, но это сложнее
                    
                    if existing_channel:
                        await bot.send_message(
                            chat_id, 
                            message_manager.get_message('channel', 'add', 'already_exists'),
                            reply_markup=get_main_menu_keyboard() # Возвращаем главное меню
                        )
                        user_states.pop(chat_id, None)
                        session.close()
                        return

                    # 3. Проверяем права бота в канале через Telegram API
                    # Для этого нам нужен объект бота. Предполагаем, что он доступен как handlers.bot или глобально.
                    # Это может вызвать проблемы с импортами, поэтому передаем bot в функцию или делаем иначе.
                    # Пока предположим, что bot доступен.
                    try:
                        # Пытаемся получить информацию о чате
                        if channel_type == 'id':
                            chat_info = await bot.get_chat(channel_identifier)
                        elif channel_type == 'username':
                            chat_info = await bot.get_chat(f"@{channel_identifier}")
                        else:
                            raise ValueError("Неизвестный тип идентификатора канала")

                        # Проверяем, что это канал или супергруппа
                        if chat_info.type not in ['channel', 'supergroup']:
                            await bot.send_message(
                                chat_id, 
                                "❌ Указанный ресурс не является каналом или группой.",
                                reply_markup=get_main_menu_keyboard()
                            )
                            user_states.pop(chat_id, None)
                            session.close()
                            return

                        # Проверяем права бота (нам нужно право 'can_post_messages')
                        bot_member = await bot.get_chat_member(chat_info.id, (await bot.get_me()).id)
                        if not (bot_member.status in ['administrator'] and getattr(bot_member, 'can_post_messages', False)):
                            await bot.send_message(
                                chat_id, 
                                message_manager.get_message('channel', 'add', 'bot_not_admin'),
                                reply_markup=get_main_menu_keyboard()
                            )
                            user_states.pop(chat_id, None)
                            session.close()
                            return

                        # 4. Получаем или создаем пользователя
                        user = session.query(User).filter_by(telegram_id=str(message.from_user.id)).first()
                        if not user:
                            user = User(
                                telegram_id=str(message.from_user.id), 
                                username=message.from_user.username,
                                first_name=message.from_user.first_name,
                                last_name=message.from_user.last_name
                            )
                            session.add(user)
                            session.flush() # Чтобы получить user.id

                        # 5. Создаем запись о канале
                        # Проверяем, не добавлен ли этот канал другим пользователем (по telegram_id)
                        # Это не ошибка, просто у каждого пользователя свой список
                        new_channel = Channel(
                            owner_id=user.id,
                            telegram_id=str(chat_info.id), # Всегда сохраняем ID
                            username=chat_info.username, # Может быть None
                            title=chat_info.title,
                            is_public=(chat_info.username is not None),
                            # invite_link=... # Обычно бот не может получить invite link, только создать
                        )
                        session.add(new_channel)
                        session.commit()
                        
                        log_info(bot.logger, f"Канал {chat_info.title} (@{chat_info.username or chat_info.id}) добавлен пользователем {message.from_user.username} (ID: {message.from_user.id})")
                        
                        await bot.send_message(
                            chat_id, 
                            message_manager.get_message('channel', 'add', 'success'),
                            reply_markup=get_main_menu_keyboard() # Возвращаем главное меню
                        )
                        
                    except telebot.apihelper.ApiException as e:
                        # Ошибки API Telegram (канал не найден, бот не участник и т.д.)
                        log_error(bot.logger, e, f"проверка канала {channel_identifier} через API для пользователя {message.from_user.id}")
                        await bot.send_message(
                            chat_id, 
                            message_manager.get_message('channel', 'add', 'error'),
                            reply_markup=get_main_menu_keyboard()
                        )
                    except Exception as e:
                        log_error(bot.logger, e, f"проверка/добавление канала {channel_identifier} для пользователя {message.from_user.id}")
                        await bot.send_message(
                            chat_id, 
                            message_manager.get_message('channel', 'add', 'error'),
                            reply_markup=get_main_menu_keyboard()
                        )
                    finally:
                        user_states.pop(chat_id, None)
                        session.close()
                        
                except Exception as e:
                    log_error(bot.logger, e, f"обработка ввода канала от пользователя {message.from_user.id}")
                    await bot.send_message(
                        chat_id, 
                        "❌ Произошла ошибка при обработке данных канала.",
                        reply_markup=get_main_menu_keyboard()
                    )
                    user_states.pop(chat_id, None)
            

        except Exception as e:
            log_error(bot.logger, e, f"обработка сообщения в состоянии {current_state} от пользователя {message.from_user.id}")
            await bot.send_message(chat_id, "❌ Произошла ошибка. Попробуйте начать заново.", reply_markup=get_main_menu_keyboard())
            user_states.pop(chat_id, None)

    