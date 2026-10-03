"""SQLAlchemy ORM models."""
from datetime import datetime
from sqlalchemy import (
    BigInteger, DateTime, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column
from .connection import Base


class Preset(Base):
    __tablename__ = "presets"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_preset_user_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    first_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    photo_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)


class Afk(Base):
    __tablename__ = "afk"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    since: Mapped[int] = mapped_column(Integer, nullable=False)


class TrackedUser(Base):
    __tablename__ = "tracked_users"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class ActivitySession(Base):
    __tablename__ = "activity_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_note_user_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)


class Filter(Base):
    __tablename__ = "filters"
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_filter_user_kw"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    keyword: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class GameStat(Base):
    __tablename__ = "game_stats"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dice_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    slots_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jackpots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duels_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duels_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trivia_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trivia_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class HostedBot(Base):
    __tablename__ = "hosted_bots"
    bot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    token: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class Warn(Base):
    __tablename__ = "warns"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasons: Mapped[str] = mapped_column(Text, default="", nullable=False)


class WarnSetting(Base):
    __tablename__ = "warn_settings"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    soft: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Lock(Base):
    __tablename__ = "locks"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commands: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    email: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    url: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BlacklistWord(Base):
    __tablename__ = "blacklist_words"
    __table_args__ = (UniqueConstraint("chat_id", "word", name="uq_bl_word"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    word: Mapped[str] = mapped_column(String(128), nullable=False)


class BlacklistChat(Base):
    __tablename__ = "blacklist_chats"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)


class AntifloodSetting(Base):
    __tablename__ = "antiflood"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Welcome(Base):
    __tablename__ = "welcomes"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    media_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    previous: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    clean: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class PmPermit(Base):
    __tablename__ = "pmpermit"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    date: Mapped[str] = mapped_column(String(32), default="", nullable=False)


class Schedule(Base):
    __tablename__ = "schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    msg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    botlog_chat: Mapped[int] = mapped_column(BigInteger, nullable=False)
    botlog_msg: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    day_of_week: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class BotFlag(Base):
    __tablename__ = "bot_flags"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
