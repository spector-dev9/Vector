from .defaults import Defaults
from .environment import Environment


class Config:
    API_ID = Environment.API_ID
    API_HASH = Environment.API_HASH
    ACCOUNTS = Environment.ACCOUNTS
    SESSION_STRING = Environment.SESSION_STRING
    PHONE_NUMBER = Environment.PHONE_NUMBER
    CMD_PREFIX = Environment.CMD_PREFIX
    LOG_LEVEL = Environment.LOG_LEVEL
    DEBUG_MODE = Environment.DEBUG_MODE
    SUDO_USERS = Environment.SUDO_USERS
    GROQ_KEY = Environment.GROQ_KEY
    GROQ_MODELS = Environment.GROQ_MODELS
    CONTROL_BOT_TOKEN = Environment.CONTROL_BOT_TOKEN
    CONTROL_BOT_ADMIN_ID = Environment.CONTROL_BOT_ADMIN_ID
    BASE_DIR = Environment.BASE_DIR
    DATA_DIR = Environment.DATA_DIR
    ACCOUNTS_DIR = Environment.ACCOUNTS_DIR
    LOGS_DIR = Environment.LOGS_DIR
    VERSION = Defaults.BOT_VERSION
    NAME = Defaults.BOT_NAME
    ASCII = Defaults.BOT_ASCII
    AUTHOR = Defaults.BOT_AUTHOR
    MAX_MESSAGE_LENGTH = Defaults.MAX_MESSAGE_LENGTH
    MAX_CAPTION_LENGTH = Defaults.MAX_CAPTION_LENGTH

    @classmethod
    def validate(cls):
        errors = []
        if not cls.API_ID:
            errors.append("API_ID is not set or invalid")
        if not cls.API_HASH:
            errors.append("API_HASH is not set")
        if not cls.ACCOUNTS:
            errors.append("ACCOUNTS must list at least one account id")
        if errors:
            pretty = "\n".join(f"  ✗ {e}" for e in errors)
            raise ValueError(f"\n⚠️  Configuration errors:\n{pretty}\n\nCheck .env")
        Environment.create_directories()
        return True

    @classmethod
    def get_info(cls):
        return {
            "version": cls.VERSION,
            "name": cls.NAME,
            "prefix": cls.CMD_PREFIX,
            "debug": cls.DEBUG_MODE,
            "accounts": cls.ACCOUNTS,
            "sudo_users": len(cls.SUDO_USERS),
            "controller_enabled": bool(cls.CONTROL_BOT_TOKEN),
        }
