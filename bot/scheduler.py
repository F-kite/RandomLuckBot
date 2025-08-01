import asyncio
import telebot
from telebot import types
import logging
from datetime import datetime
import pytz
import random
from sqlalchemy import and_
from db import SessionLocal
from models import Giveaway, GiveawayParticipant,  Channel, Winner, User
from utils import log_info, log_error

import telebot.apihelper

async def publish_scheduled_giveaways(bot):
    """Публикует розыгрыши, время публикации которых наступило"""
    session = SessionLocal()
    try:
        # Определяем "сейчас" 
        # Важно: убедитесь, что формат времени в БД согласован с этим
        now = datetime.now(pytz.utc) # Если в БД хранится "наивный" datetime, предполагающий локальное время
        
        # Находим розыгрыши в статусе 'pending' с publication_time <= now
        giveaways_to_publish = session.query(Giveaway).filter(
            and_(
                Giveaway.status == 'pending',
                Giveaway.publication_time <= now
            )
        ).all()

        for giveaway in giveaways_to_publish:
            try:
                # 1. Получаем информацию о канале из БД
                channel_db_obj = session.query(Channel).get(giveaway.channel_id)
                if not channel_db_obj:
                    log_error(bot.logger, f"Канал для розыгрыша {giveaway.id} не найден в БД", "публикация")
                    # Можно установить статус 'error' или оставить 'pending' для повторной попытки
                    # giveaway.status = 'error'
                    # session.commit()
                    continue
                
                # Проверяем, есть ли у канала username (необходим для публикации по @username)
                if not channel_db_obj.username:
                    log_error(bot.logger, f"Канал для розыгрыша {giveaway.id} не имеет @username и не может быть использован для публикации", "публикация")
                    # giveaway.status = 'error_channel_no_username'
                    # session.commit()
                    continue
                
                channel_username = channel_db_obj.username
                channel_title = channel_db_obj.title or channel_username

                # 2. Создаем inline-кнопку для участия
                # Используем f-строку для формирования callback_data
                markup = types.InlineKeyboardMarkup()
                button_text = giveaway.participation_button_text or "Участвовать" # На всякий случай, если NULL
                callback_data = f"enter_giveaway:{giveaway.id}"
                markup.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
                
                # 3. Формируем текст сообщения
                # Можно сделать более сложное форматирование
                description = giveaway.description or "Розыгрыш!"
                prize = giveaway.prize or "Приз не указан"
                
                caption_text = f"{description}\n\n🎁 <b>Приз:</b> {prize}"
                message_text = f"{description}\n\n🎁 Приз: {prize}"
                
                # 4. Отправляем сообщение в зависимости от типа медиа
                sent_message = None
                try:
                    if giveaway.media_type == 'photo' and giveaway.media_file_id:
                        # Отправляем фото с подписью
                        sent_message = await bot.send_photo(
                            chat_id=f"@{channel_username}", 
                            photo=giveaway.media_file_id, 
                            caption=caption_text,
                            parse_mode='HTML', # Включаем HTML разметку
                            reply_markup=markup
                        )
                    elif giveaway.media_type == 'video' and giveaway.media_file_id:
                        # Отправляем видео с подписью
                        sent_message = await bot.send_video(
                            chat_id=f"@{channel_username}", 
                            video=giveaway.media_file_id, 
                            caption=caption_text,
                            parse_mode='HTML',
                            reply_markup=markup
                        )
                    elif giveaway.media_type == 'animation' and giveaway.media_file_id:
                        # Отправляем GIF (анимацию) с подписью
                        sent_message = await bot.send_animation(
                            chat_id=f"@{channel_username}", 
                            animation=giveaway.media_file_id, 
                            caption=caption_text,
                            parse_mode='HTML',
                            reply_markup=markup
                        )
                    elif giveaway.media_type == 'document' and giveaway.media_file_id:
                         # Отправляем документ (например, изображение как документ) с подписью
                         sent_message = await bot.send_document(
                            chat_id=f"@{channel_username}", 
                            document=giveaway.media_file_id, 
                            caption=caption_text,
                            parse_mode='HTML',
                            reply_markup=markup
                        )
                    else: # Без медиа или неизвестный тип
                        # Отправляем обычное текстовое сообщение
                        sent_message = await bot.send_message(
                            chat_id=f"@{channel_username}", 
                            text=message_text,
                            parse_mode='HTML',
                            reply_markup=markup
                        )
                    
                    # 5. Обновляем запись в БД
                    if sent_message:
                        giveaway.message_id = sent_message.message_id
                        giveaway.status = 'active'
                        session.commit()
                        log_info(bot.logger, f"✅ Розыгрыш {giveaway.id} успешно опубликован в канале @{channel_username} (сообщение ID: {sent_message.message_id})")
                    else:
                        # Теоретически не должно произойти, но на всякий случай
                        log_error(bot.logger, f"Не удалось опубликовать розыгрыш {giveaway.id}: send_message вернул None", "публикация")
                        # Можно установить статус ошибки
                        giveaway.status = 'error_publish_failed'
                        session.commit()
                        
                except telebot.apihelper.ApiException as e:
                    # Ошибки API Telegram (канал не найден, бот не админ, нет прав и т.д.)
                    error_msg = str(e)
                    log_error(bot.logger, f"Ошибка API Telegram при публикации розыгрыша {giveaway.id} в канал @{channel_username}: {error_msg}", "публикация")
                    
                    # Можно установить специальный статус в зависимости от типа ошибки
                    if "Bad Request: chat not found" in error_msg:
                        giveaway.status = 'error_channel_not_found'
                    elif "Forbidden: bot is not a member" in error_msg or "Forbidden: bot was kicked" in error_msg:
                        giveaway.status = 'error_bot_not_member'
                    elif "Bad Request: not enough rights to send" in error_msg:
                        giveaway.status = 'error_no_rights'
                    else:
                        giveaway.status = 'error_telegram_api'
                    session.commit()
                    
                except Exception as e:
                    # Другие ошибки (например, проблемы с сетью)
                    log_error(bot.logger, e, f"неожиданная ошибка при публикации розыгрыша {giveaway.id} в канал @{channel_username}")
                    giveaway.status = 'error_unexpected'
                    session.commit()

            except Exception as e:
                session.rollback()
                log_error(bot.logger, e, f"публикация розыгрыша {giveaway.id}")

    except Exception as e:
        log_error(bot.logger, e, "планировщик публикации")
    finally:
        session.close()

async def finish_giveaways_by_time(bot):
    """Завершает розыгрыши, время окончания которых наступило (если условие 'time')"""
    session = SessionLocal()
    try:
        now = datetime.now(pytz.utc) 
        
        giveaways_to_finish = session.query(Giveaway).filter(
            and_(
                Giveaway.status == 'active',
                Giveaway.end_condition_type == 'time',
                Giveaway.end_time <= now
            )
        ).all()

        for giveaway in giveaways_to_finish:
            try:
                log_info(bot.logger, f"Начинаем завершение розыгрыша {giveaway.id} по времени")
                
                # 1. Выбираем победителей
                winners = await select_winners(session, giveaway)
                
                if winners is None:
                    # Ошибка при выборе победителей
                    giveaway.status = 'error_winner_selection'
                    session.commit()
                    log_error(bot.logger, f"Ошибка при выборе победителей для розыгрыша {giveaway.id}", "завершение по времени")
                    continue
                
                if not winners:
                    # Нет участников
                    log_info(bot.logger, f"Розыгрыш {giveaway.id} завершен: нет участников")
                    await publish_results(bot, session, giveaway, [])
                    giveaway.status = 'completed_no_participants'
                    session.commit()
                    continue

                # 2. Сохраняем победителей в БД
                for i, participant in enumerate(winners):
                    place = i + 1
                    winner_record = Winner(
                        lottery_id=giveaway.id, # Обратите внимание на имя поля в модели
                        participant_id=participant.id,
                        place=place,
                        is_additional=False
                    )
                    session.add(winner_record)
                
                session.commit()
                
                # 3. Публикуем результаты в канал
                await publish_results(bot, session, giveaway, winners)
                
                # 4. Отправляем уведомление создателю (опционально)
                await notify_creator(bot, session, giveaway, winners)
                
                # 5. Обновляем статус розыгрыша
                giveaway.status = 'completed'
                session.commit()
                
                log_info(bot.logger, f"Розыгрыш {giveaway.id} успешно завершен по времени. Выбрано {len(winners)} победителей.")
                
            except Exception as e:
                session.rollback()
                log_error(bot.logger, e, f"завершение розыгрыша {giveaway.id} по времени")

    except Exception as e:
        log_error(bot.logger, e, "планировщик завершения по времени")
    finally:
        session.close()

async def check_giveaways_by_participants(bot):
    """Проверяет, нужно ли завершить розыгрыши по количеству участников"""
    session = SessionLocal()
    try:
        # Находим активные розыгрыши с условием 'participants'
        active_participant_giveaways = session.query(Giveaway).filter(
            and_(
                Giveaway.status == 'active',
                Giveaway.end_condition_type == 'participants'
            )
        ).all()

        for giveaway in active_participant_giveaways:
            try:
                now = datetime.now(pytz.utc)
                
                # Подсчитываем участников
                participant_count = session.query(GiveawayParticipant).filter_by(giveaway_id=giveaway.id).count()
                
                if participant_count >= giveaway.end_participants_count:
                    log_info(bot.logger, f"Начинаем завершение розыгрыша {giveaway.id} по количеству участников ({participant_count}>={giveaway.end_participants_count})")
                
                    # 1. Выбираем победителей
                    winners = await select_winners(session, giveaway)
                    
                    if winners is None:
                        # Ошибка при выборе победителей
                        giveaway.status = 'error_winner_selection'
                        session.commit()
                        log_error(bot.logger, f"Ошибка при выборе победителей для розыгрыша {giveaway.id}", "завершение по участникам")
                        continue
                    
                    if not winners:
                        # Нет участников (теоретически возможно, если участники были удалены)
                        log_info(bot.logger, f"Розыгрыш {giveaway.id} завершен: нет участников")
                        await publish_results(bot, session, giveaway, [])
                        giveaway.status = 'completed_no_participants'
                        session.commit()
                        continue

                    # 2. Сохраняем победителей в БД
                    for i, participant in enumerate(winners):
                        place = i + 1
                        winner_record = Winner(
                            lottery_id=giveaway.id, # Обратите внимание на имя поля в модели
                            participant_id=participant.id,
                            place=place,
                            is_additional=False
                        )
                        session.add(winner_record)
                    
                    session.commit()
                    
                    # 3. Публикуем результаты в канал
                    await publish_results(bot, session, giveaway, winners)
                    
                    # 4. Отправляем уведомление создателю (опционально)
                    await notify_creator(bot, session, giveaway, winners)
                    
                    # 5. Обновляем статус розыгрыша
                    giveaway.status = 'completed'
                    session.commit()
                    
                    log_info(bot.logger, f"Розыгрыш {giveaway.id} успешно завершен по количеству участников. Выбрано {len(winners)} победителей.")
                    
            except Exception as e:
                session.rollback()
                log_error(bot.logger, e, f"проверка участников розыгрыша {giveaway.id}")

    except Exception as e:
        log_error(bot.logger, e, "планировщик проверки по участникам")
    finally:
        session.close()

# --- Вспомогательные функции ---

async def select_winners(session, giveaway: Giveaway):
    """
    Выбирает победителей розыгрыша случайным образом.
    Возвращает список GiveawayParticipant или None в случае ошибки.
    """
    try:
        # Получаем всех участников
        participants = session.query(GiveawayParticipant).filter_by(giveaway_id=giveaway.id).all()
        
        if not participants:
            return [] # Нет участников
            
        winners_count = giveaway.winners_count
        
        # Если участников меньше, чем положено победителей, выбираем всех
        if len(participants) <= winners_count:
            return participants
            
        # Выбираем случайных победителей
        # Используем random.sample для получения уникальных значений
        selected_winners = random.sample(participants, winners_count)
        return selected_winners
        
    except Exception as e:
        log_error(None, e, f"выбор победителей для розыгрыша {giveaway.id}") # logger будет передан из вызывающей функции
        return None

async def publish_results(bot, session, giveaway: Giveaway, winners: list):
    """
    Публикует результаты розыгрыша в канал.
    """
    try:
        # 1. Получаем информацию о канале
        channel_db_obj = session.query(Channel).get(giveaway.channel_id)
        if not channel_db_obj or not channel_db_obj.username:
            log_error(bot.logger, f"Канал для публикации результатов розыгрыша {giveaway.id} не найден или не имеет @username", "публикация результатов")
            return

        channel_username = channel_db_obj.username
        channel_title = channel_db_obj.title or channel_username

        # 2. Формируем текст сообщения с результатами
        if not winners:
            results_text = f"🎉 <b>Розыгрыш завершен!</b>\n\n"
            results_text += f"К сожалению, в розыгрыше никто не принял участие.\n\n"
            results_text += f"<s>{giveaway.description or 'Розыгрыш'}</s>\n"
            results_text += f"Приз: <s>{giveaway.prize or 'Не указан'}</s>"
        else:
            results_text = f"🎉 <b>Результаты розыгрыша!</b>\n\n"
            results_text += f"<s>{giveaway.description or 'Розыгрыш'}</s>\n"
            results_text += f"Приз: <s>{giveaway.prize or 'Не указан'}</s>\n\n"
            results_text += f"🏆 <b>Победители:</b>\n"
            
            for i, winner in enumerate(winners):
                place = i + 1
                # Формируем имя пользователя
                if winner.username:
                    user_mention = f"@{winner.username}"
                else:
                    # Если нет username, можно использовать first_name или просто ID
                    display_name = winner.first_name or f"Участник {winner.telegram_user_id}"
                    user_mention = f"<a href='tg://user?id={winner.telegram_user_id}'>{display_name}</a>"
                
                results_text += f"{place}. {user_mention}\n"
            
            # Добавляем ссылку на оригинальный розыгрыш, если он был опубликован
            if giveaway.message_id:
                results_text += f"\n<a href='https://t.me/{channel_username}/{giveaway.message_id}'>Посмотреть розыгрыш</a>"

        # 3. Отправляем сообщение с результатами в канал
        try:
            sent_message = await bot.send_message(
                chat_id=f"@{channel_username}",
                text=results_text,
                parse_mode='HTML'
            )
            log_info(bot.logger, f"Результаты розыгрыша {giveaway.id} опубликованы в канале @{channel_username}")
            
        except telebot.apihelper.ApiException as e:
            error_msg = str(e)
            log_error(bot.logger, f"Ошибка API Telegram при публикации результатов розыгрыша {giveaway.id} в канал @{channel_username}: {error_msg}", "публикация результатов")
            
    except Exception as e:
        log_error(bot.logger, e, f"публикация результатов розыгрыша {giveaway.id}")

async def notify_creator(bot, session, giveaway: Giveaway, winners: list):
    """
    Отправляет уведомление создателю розыгрыша о его завершении.
    (Эту функцию можно реализовать позже, если нужно)
    """
    try:
        creator = session.query(User).get(giveaway.creator_id)
        if not creator:
            log_info(bot.logger, f"Создатель розыгрыша {giveaway.id} не найден для уведомления")
            return
            
        creator_telegram_id = creator.telegram_id
        
        # Формируем текст уведомления
        notification_text = f"Ваш розыгрыш (ID: {giveaway.id}) был завершен.\n"
        if winners:
            notification_text += f"Победители:\n"
            for i, winner in enumerate(winners):
                username = winner.username or winner.first_name or winner.telegram_user_id
                notification_text += f"{i+1}. {username}\n"
        else:
            notification_text += "Победителей нет."
        
        # Отправляем уведомление
        await bot.send_message(chat_id=creator_telegram_id, text=notification_text)
        log_info(bot.logger, f"Уведомление о завершении розыгрыша {giveaway.id} отправлено создателю {creator.username or creator.telegram_id}")
        
    except telebot.apihelper.ApiException as e:
        if "Forbidden" in str(e):
            log_info(bot.logger, f"Не удалось уведомить создателя розыгрыша {giveaway.id}: пользователь не начал чат с ботом")
        else:
            log_error(bot.logger, e, f"отправка уведомления создателю розыгрыша {giveaway.id}")
    except Exception as e:
        log_error(bot.logger, e, f"уведомление создателя розыгрыша {giveaway.id}")


async def run_scheduler(bot, interval=60): # Проверяем каждую минуту
    """Основной цикл планировщика"""
    log_info(bot.logger, "⏰ Планировщик задач запущен")
    while True:
        try:
            await publish_scheduled_giveaways(bot)
            await finish_giveaways_by_time(bot)
            await check_giveaways_by_participants(bot)
        except Exception as e:
            log_error(bot.logger, e, "основной цикл планировщика")
        await asyncio.sleep(interval)
