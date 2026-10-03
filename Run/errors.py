"""Per-account error history — bounded ring buffer.

Distinct from the file logger:
  • scoped per AccountContext
  • structured records (type, context, timestamp, traceback)
  • instantly readable from within the running process
  • bounded memory (default 100 entries)
"""
from __future__ import annotations
import traceback
from collections import deque
from datetime import datetime
from typing import Optional

from core.logger import setup_logger

logger = setup_logger("VECTOR.errors")


class ErrorHandler:
    __slots__ = ("_log", "max_errors")

    def __init__(self, max_errors: int = 100):
        self._log: deque = deque(maxlen=max_errors)
        self.max_errors = max_errors

    def log_error(self, error: BaseException, context: Optional[str] = None) -> None:
        self._log.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "type": type(error).__name__,
            "error": str(error)[:500],
            "context": context or "—",
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )[:2000],
        })

    def get_recent_errors(self, count: int = 10) -> list:
        n = max(1, min(int(count), self.max_errors))
        return list(self._log)[-n:]

    def clear(self) -> None:
        self._log.clear()

    def __len__(self) -> int:
        return len(self._log)
