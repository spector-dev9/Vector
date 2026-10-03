"""Per-account schema creation."""
from core.logger import setup_logger
from .connection import AccountDatabase

logger = setup_logger("VECTOR.migrations")


async def run_for(db: AccountDatabase) -> None:
    await db.create_all()
    logger.info(f"[{db.account_id}] ✅ migrations complete")
