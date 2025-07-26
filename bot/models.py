from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Table
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    giveaways = relationship('Giveaway', back_populates='creator')
    channels = relationship('Channel', back_populates='owner')

class Channel(Base):
    __tablename__ = 'channels'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    title = Column(String)
    owner_id = Column(Integer, ForeignKey('users.id'))
    owner = relationship('User', back_populates='channels')
    giveaways = relationship('GiveawayChannel', back_populates='channel')

class Giveaway(Base):
    __tablename__ = 'giveaways'
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey('users.id'))
    creator = relationship('User', back_populates='giveaways')
    description = Column(Text)
    prize = Column(String)
    media_type = Column(String)  # photo, video, gif
    media_file_id = Column(String)
    winners_count = Column(Integer)
    end_datetime = Column(DateTime)
    end_by_participants = Column(Boolean, default=False)
    participants_limit = Column(Integer, nullable=True)
    join_button_text = Column(String, default='Участвовать')
    created_at = Column(DateTime, default=datetime.utcnow)
    channels = relationship('GiveawayChannel', back_populates='giveaway')
    participants = relationship('GiveawayParticipant', back_populates='giveaway')

class GiveawayChannel(Base):
    __tablename__ = 'giveaway_channels'
    id = Column(Integer, primary_key=True)
    giveaway_id = Column(Integer, ForeignKey('giveaways.id'))
    channel_id = Column(Integer, ForeignKey('channels.id'))
    giveaway = relationship('Giveaway', back_populates='channels')
    channel = relationship('Channel', back_populates='giveaways')

class GiveawayParticipant(Base):
    __tablename__ = 'giveaway_participants'
    id = Column(Integer, primary_key=True)
    giveaway_id = Column(Integer, ForeignKey('giveaways.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    joined_at = Column(DateTime, default=datetime.utcnow)
    giveaway = relationship('Giveaway', back_populates='participants')

class SupportRequest(Base):
    __tablename__ = 'support_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow) 