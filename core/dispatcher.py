"""Failure-isolating dispatcher.

The per-handler try/except in core/decorators.py already isolates
handler exceptions. This module adds a second layer at the update-loop
level, but ONLY if Telethon exposes the private `_handle_update` hook
on this version. If it doesn't, we degrade gracefully instead of
killing boot.
"""
from core.logger import setup_logger

logger = setup_logger("VECTOR.dispatcher")


def install(client, ctx) -> None:
    original = getattr(client, "_handle_update", None)

    if original is None:
        logger.warning(
            f"{ctx.log_tag} dispatcher: Telethon on this install does not "
            f"expose `_handle_update` — update-loop guard NOT installed. "
            f"Per-handler isolation (core/decorators.py) is still active."
        )
        return

    async def guarded(update):
        try:
            await original(update)
        except Exception as e:
            logger.error(f"{ctx.log_tag} update handler: {e}", exc_info=True)

    try:
        client._handle_update = guarded
        logger.info(f"{ctx.log_tag} dispatcher guard installed")
    except Exception as e:
        logger.warning(f"{ctx.log_tag} dispatcher patch failed: {e}")