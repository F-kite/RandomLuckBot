from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import declarative_base, relationship

# Создаем базовый класс для моделей
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id = Column(String, unique=True, nullable=False, index=True) # Хранить как String для избежания проблем с отрицательными ID
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    giveaways = relationship('Giveaway', back_populates='creator')
    channels = relationship('Channel', back_populates='owner')
    support_requests = relationship('SupportRequest', back_populates='user')

class Channel(Base):
    __tablename__ = 'channels'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    owner_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    telegram_id = Column(String, unique=True, nullable=True) # Может быть NULL, если добавляется по ссылке или юзернейму
    username = Column(String, unique=True, nullable=True) # @username канала
    title = Column(String, nullable=True)
    # type = Column(String(50), nullable=True) # 'channel' или 'group' - можно добавить, если нужно различать
    is_public = Column(Boolean, nullable=False, default=False)
    invite_link = Column(Text, nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    owner = relationship('User', back_populates='channels')
    giveaways_assoc = relationship('GiveawayChannel', back_populates='channel')

class Giveaway(Base):
    __tablename__ = 'lotteries'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    creator_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    channel_id = Column(BigInteger, ForeignKey('channels.id', ondelete='CASCADE'), nullable=False, index=True) # Основной канал розыгрыша
    message_id = Column(BigInteger, nullable=True) # ID сообщения после публикации в канале

    # title = Column(String(255), nullable=True) # Можно добавить, если нужно отдельное поле заголовка
    description = Column(Text) # Описание розыгрыша
    prize = Column(String) # Приз

    media_type = Column(String) # 'photo', 'video', 'animation', 'document', 'none'
    media_file_id = Column(String) # file_id медиа из Telegram

    participation_button_text = Column(String, default='Участвовать')
    # required_channels - реализовано через ассоциативную таблицу GiveawayChannel
    winners_count = Column(Integer, nullable=False) # CHECK (winners_count > 0) - проверка на уровне приложения

    publication_time = Column(DateTime(timezone=True), nullable=True, index=True) # Время публикации розыгрыша
    # Поля для гибкого завершения
    end_condition_type = Column(String(20), nullable=False, default='time') # 'time' или 'participants'
    end_time = Column(DateTime(timezone=True), nullable=True, index=True) # Время завершения (если по времени)
    end_participants_count = Column(Integer, nullable=True) # Кол-во участников для завершения (если по участникам)

    has_captcha = Column(Boolean, nullable=False, default=False) # Есть ли капча
    # captcha_type = Column(String, nullable=True) # Тип капчи (например, 'simple', 'math') - можно добавить позже
    boost_enabled = Column(Boolean, nullable=False, default=False) # Включена ли система бустов
    # boost_channels - первые N из GiveawayChannel, определяется логикой

    status = Column(String(30), nullable=False, default='pending', index=True) # 'pending', 'active', 'completed', 'completed_no_participants', 'error_winner_selection'

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Связи
    creator = relationship('User', back_populates='giveaways')
    main_channel = relationship('Channel') # Основной канал
    channels_assoc = relationship('GiveawayChannel', back_populates='giveaway', cascade="all, delete-orphan")
    participants = relationship('GiveawayParticipant', back_populates='giveaway', cascade="all, delete-orphan")
    winners = relationship('Winner', back_populates='lottery', cascade="all, delete-orphan")


# Ассоциативная таблица для связи М:М между Giveaway и Channel (обязательные подписки)
class GiveawayChannel(Base):
    __tablename__ = 'giveaway_channels'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    giveaway_id = Column(BigInteger, ForeignKey('lotteries.id', ondelete='CASCADE'), nullable=False, index=True)
    channel_id = Column(BigInteger, ForeignKey('channels.id', ondelete='CASCADE'), nullable=False, index=True)

    # Уникальность: один канал не должен быть добавлен дважды к одному розыгрышу
    __table_args__ = (UniqueConstraint('giveaway_id', 'channel_id', name='uq_giveaway_channel'),)

    # Связи
    giveaway = relationship('Giveaway', back_populates='channels_assoc')
    channel = relationship('Channel', back_populates='giveaways_assoc')

class GiveawayParticipant(Base):
    __tablename__ = 'participants'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    giveaway_id = Column(BigInteger, ForeignKey('lotteries.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True) # Связь с глобальным пользователем
    telegram_user_id = Column(BigInteger, nullable=False, index=True) # ID пользователя в Telegram (дублируем для быстрого поиска?)

    username = Column(String, nullable=True) # Username на момент участия
    first_name = Column(String, nullable=True) # Имя на момент участия
    last_name = Column(String, nullable=True) # Фамилия на момент участия

    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    captcha_passed = Column(Boolean, nullable=False, default=False) # Прошел ли капчу

    # Уникальность: один пользователь - одно участие в одном розыгрыше
    __table_args__ = (UniqueConstraint('giveaway_id', 'telegram_user_id', name='uq_participant_giveaway_user'),)

    # Связи
    giveaway = relationship('Giveaway', back_populates='participants')
    user = relationship('User') # Связь с глобальным пользователем

class Winner(Base):
    __tablename__ = 'winners'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    lottery_id = Column(BigInteger, ForeignKey('lotteries.id', ondelete='CASCADE'), nullable=False, index=True) # ID розыгрыша
    participant_id = Column(BigInteger, ForeignKey('participants.id', ondelete='CASCADE'), nullable=False) # Связь с участником

    place = Column(Integer, nullable=False) # Место (1, 2, 3...)
    is_additional = Column(Boolean, nullable=False, default=False) # Является ли дополнительным победителем?

    awarded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Уникальность места и участника в рамках розыгрыша
    __table_args__ = (
        UniqueConstraint('lottery_id', 'place', name='uq_winner_lottery_place'),
        UniqueConstraint('lottery_id', 'participant_id', name='uq_winner_lottery_participant'),
    )

    # Связи
    lottery = relationship('Giveaway', back_populates='winners')
    participant = relationship('GiveawayParticipant')

class SupportRequest(Base):
    __tablename__ = 'support_requests'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'), nullable=True) # Позволим NULL, если пользователь не зарегистр.
    message = Column(Text, nullable=False) # Сообщение не может быть пустым
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_resolved = Column(Boolean, nullable=False, default=False) # Статус запроса

    # Связи
    user = relationship('User', back_populates='support_requests')

# Индексы (если не указаны inline)
# Index('idx_users_telegram_id', User.telegram_id)
# Index('idx_channels_owner_id', Channel.owner_id)
# Index('idx_giveaways_creator_id', Giveaway.creator_id)
# Index('idx_giveaways_channel_id', Giveaway.channel_id)
# Index('idx_giveaways_status', Giveaway.status)
# Index('idx_giveaways_end_time', Giveaway.end_time)
# Index('idx_participants_giveaway_id', GiveawayParticipant.giveaway_id)
# Index('idx_participants_telegram_user_id', GiveawayParticipant.telegram_user_id)
# Index('idx_winners_lottery_id', Winner.lottery_id)