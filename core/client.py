"""VectorClient — a TelegramClient bound to one AccountContext."""
from __future__ import annotations
from telethon import TelegramClient
from telethon.sessions import StringSession
from Config.settings import Config
from core.logger import setup_logger, account_logger

logger = setup_logger("VECTOR.client")

# ── one-time patch: event.ctx resolves to the account bound to the client ──
try:
    from telethon.events.common import EventCommon
    if not isinstance(getattr(EventCommon, "ctx", None), property):
        EventCommon.ctx = property(
            lambda self: getattr(getattr(self, "client", None), "ctx", None)
        )
except Exception as _e:
    logger.warning(f"EventCommon.ctx patch skipped: {_e}")


class VectorClient:
    def __init__(self, account_id: str, paths, session_string: str = "", phone: str = ""):
        self.account_id = account_id
        self.paths = paths
        self._phone = phone
        self._log = account_logger(account_id, "client")

        if session_string:
            self.client = TelegramClient(
                StringSession(session_string),
                Config.API_ID, Config.API_HASH,
                device_model=f"{Config.NAME} v{Config.VERSION}",
                system_version="Linux",
                app_version=Config.VERSION,
            )
            self._use_string = True
        else:
            self.client = TelegramClient(
                str(paths.session),
                Config.API_ID, Config.API_HASH,
                device_model=f"{Config.NAME} v{Config.VERSION}",
                system_version="Linux",
                app_version=Config.VERSION,
            )
            self._use_string = False

        self.ctx = None
        self._me = None

    def __call__(self, *args, **kwargs):
        return self.client(*args, **kwargs)

    async def start(self) -> None:
        if self._use_string:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                raise RuntimeError(
                    f"SESSION_STRING for account '{self.account_id}' is invalid or expired."
                )
        else:
            if not self._phone:
                raise RuntimeError(
                    f"No phone or session string for account '{self.account_id}'."
                )
            await self.client.start(phone=self._phone)
        self._me = await self.client.get_me()
        self._log.info(f"✅ Logged in as {self._me.first_name} (id={self._me.id})")

    async def stop(self) -> None:
        try:
            await self.client.disconnect()
            self._log.info("✅ Disconnected")
        except Exception as e:
            self._log.error(f"stop failed: {e}")

    @property
    def me(self):
        return self._me

    def __getattr__(self, name):
        return getattr(self.client, name)
