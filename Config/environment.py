"""Environment loader — account-aware."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _int_env(name, default=0):
    v = os.getenv(name, str(default)).strip()
    try:
        return int(v)
    except ValueError:
        return default


def _bool_env(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _list_env(name):
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


class Environment:
    API_ID = _int_env("API_ID")
    API_HASH = os.getenv("API_HASH", "").strip()
    ACCOUNTS = _list_env("ACCOUNTS") or ["main"]
    SESSION_STRING = os.getenv("SESSION_STRING", "").strip()
    PHONE_NUMBER = os.getenv("PHONE_NUMBER", "").strip()
    CMD_PREFIX = os.getenv("CMD_PREFIX", ".").strip() or "."
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    DEBUG_MODE = _bool_env("DEBUG_MODE", False)
    SUDO_USERS = [int(x) for x in _list_env("SUDO_USERS") if x.lstrip("-").isdigit()]
    GROQ_KEY = os.getenv("GROQ_KEY", "").strip()
    GROQ_MODELS = _list_env("GROQ_MODELS") or [
        "openai/gpt-oss-120b",
        "llama-3.1-8b-instant",
        "qwen/qwen3-32b",
    ]
    CONTROL_BOT_TOKEN = os.getenv("CONTROL_BOT_TOKEN", "").strip()
    CONTROL_BOT_ADMIN_ID = _int_env("CONTROL_BOT_ADMIN_ID")
    BASE_DIR = BASE_DIR
    DATA_DIR = BASE_DIR / "data"
    ACCOUNTS_DIR = DATA_DIR / "accounts"
    LOGS_DIR = DATA_DIR / "logs"

    @classmethod
    def create_directories(cls):
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def session_string_for(cls, account_id):
        env = f"SESSION_STRING_{account_id.upper().replace('-', '_')}"
        specific = os.getenv(env, "").strip()
        if specific:
            return specific
        if account_id == cls.ACCOUNTS[0] and cls.SESSION_STRING:
            return cls.SESSION_STRING
        return ""

    @classmethod
    def phone_for(cls, account_id):
        env = f"PHONE_{account_id.upper().replace('-', '_')}"
        return os.getenv(env, "").strip() or cls.PHONE_NUMBER
