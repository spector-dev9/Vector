"""Account-scoped SQLAlchemy."""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.logger import setup_logger

logger = setup_logger("VECTOR.db")


class Base(DeclarativeBase):
    pass


class AccountDatabase:
    def __init__(self, account_id: str, db_path: Path):
        self.account_id = account_id
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine = create_async_engine(
            url, echo=False, future=True, pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False,
        )
        self._log_tag = f"[{account_id}]"

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_all(self) -> None:
        from . import models  # noqa: F401
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(f"{self._log_tag} migrations applied → {self.db_path.name}")

    async def dispose(self) -> None:
        await self.engine.dispose()
        logger.info(f"{self._log_tag} engine disposed")

    def __repr__(self):
        return f"<AccountDatabase {self.account_id} @ {self.db_path}>"
