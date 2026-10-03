"""Account-aware logging."""
import logging
import sys
from datetime import datetime
from Config.settings import Config


class _ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m", "INFO": "\033[32m", "WARNING": "\033[33m",
        "ERROR": "\033[31m", "CRITICAL": "\033[35m", "RESET": "\033[0m",
    }

    def format(self, record):
        if not hasattr(record, "acc"):
            record.acc = ""
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        original = record.levelname
        record.levelname = f"{color}{original}{self.COLORS['RESET']}"
        try:
            return super().format(record)
        finally:
            record.levelname = original


class _FileFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, "acc"):
            record.acc = ""
        return super().format(record)


_CONFIGURED: set[str] = set()


def setup_logger(name: str = "VECTOR") -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _CONFIGURED:
        return logger
    _CONFIGURED.add(name)

    logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
    Config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_ColoredFormatter("%(levelname)s %(acc)s %(message)s"))

    logfile = Config.LOGS_DIR / f"vector_{datetime.now():%Y%m%d}.log"
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FileFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(acc)s - %(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logger.addHandler(console)
    logger.addHandler(fh)
    logger.propagate = False
    return logger


def account_logger(account_id: str, name: str) -> logging.LoggerAdapter:
    base = setup_logger(f"VECTOR.{name}")
    return logging.LoggerAdapter(base, {"acc": f"[{account_id}]"})
