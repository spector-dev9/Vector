"""Typing animation."""
import asyncio
from core.logger import setup_logger

logger = setup_logger("VECTOR.anim")

_state = {"enabled": True}


def enabled():
    return _state["enabled"]


def set_enabled(value):
    _state["enabled"] = bool(value)


async def _keep(client, chat_id, action):
    while True:
        try:
            async with client.action(chat_id, action):
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)


class _Ctx:
    __slots__ = ("client", "chat_id", "action", "task")

    def __init__(self, client, chat_id, action):
        self.client = client
        self.chat_id = chat_id
        self.action = action
        self.task = None

    async def __aenter__(self):
        if not _state["enabled"]:
            return self
        try:
            self.task = asyncio.create_task(
                _keep(self.client, self.chat_id, self.action)
            )
        except Exception:
            pass
        return self

    async def __aexit__(self, *_):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except BaseException:
                pass
            self.task = None
        return False


def typing(client, chat_id, action="typing"):
    return _Ctx(client, chat_id, action)


async def quick_typing(client, chat_id, seconds=0.4):
    if not _state["enabled"]:
        return
    try:
        async with client.action(chat_id, "typing"):
            await asyncio.sleep(seconds)
    except Exception:
        pass
