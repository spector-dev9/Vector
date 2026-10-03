"""Graceful shutdown."""
import signal
import sys
from core.logger import setup_logger

logger = setup_logger("VECTOR.shutdown")


class ShutdownHandler:
    def __init__(self, manager):
        self.manager = manager
        self._fired = False

    def setup(self):
        signal.signal(signal.SIGINT, self._sig)
        signal.signal(signal.SIGTERM, self._sig)

    def _sig(self, signum, _frame):
        if self._fired:
            return
        self._fired = True
        logger.info(f"🛑 shutdown signal ({signum})")
        sys.exit(0)
