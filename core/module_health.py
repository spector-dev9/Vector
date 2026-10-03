"""Per-account module health — auto-disable handlers that keep failing.

Policy:
  • 5 failures in a 60s sliding window disables the handler for the
    rest of the session (or until `.modenable` is issued).
  • Disable is per-account, per-handler-name.
  • Silent skip once disabled — no error spam.
"""
from __future__ import annotations
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Set

from core.logger import setup_logger

logger = setup_logger("VECTOR.module_health")


class ModuleHealth:
    __slots__ = ("account_id", "threshold", "window", "_failures", "_disabled")

    def __init__(self, account_id: str, threshold: int = 5, window: int = 60):
        self.account_id = account_id
        self.threshold = threshold
        self.window = window
        self._failures: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=threshold)
        )
        self._disabled: Set[str] = set()

    def record_failure(self, handler_name: str) -> bool:
        """Return True if the handler just got disabled."""
        now = time.time()
        bucket = self._failures[handler_name]
        bucket.append(now)
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.threshold and handler_name not in self._disabled:
            self._disabled.add(handler_name)
            return True
        return False

    def record_success(self, handler_name: str) -> None:
        """Clear failure history on success."""
        self._failures.pop(handler_name, None)

    def disable(self, handler_name: str) -> bool:
        """Manually disable a handler for this session."""
        if handler_name in self._disabled:
            return False
        self._disabled.add(handler_name)
        return True

    def is_disabled(self, handler_name: str) -> bool:
        return handler_name in self._disabled

    def re_enable(self, handler_name: str) -> bool:
        if handler_name in self._disabled:
            self._disabled.discard(handler_name)
            self._failures.pop(handler_name, None)
            return True
        return False

    def re_enable_all(self) -> int:
        n = len(self._disabled)
        self._disabled.clear()
        self._failures.clear()
        return n

    def disabled_list(self) -> list:
        return sorted(self._disabled)

    def __repr__(self) -> str:
        return f"<ModuleHealth {self.account_id} disabled={len(self._disabled)}>"
