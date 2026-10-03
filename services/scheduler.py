"""Tiny asyncio scheduler."""
import asyncio
from core.logger import setup_logger

logger = setup_logger("VECTOR.scheduler")


class Scheduler:
    def __init__(self):
        self._tasks = []

    def every(self, seconds, fn):
        async def loop():
            while True:
                try:
                    await asyncio.sleep(seconds)
                    await fn()
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    logger.warning(f"scheduler task: {e}")
        task = asyncio.create_task(loop())
        self._tasks.append(task)
        return task

    def stop_all(self):
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
