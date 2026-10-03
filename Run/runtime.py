"""Account runtime."""
from __future__ import annotations
import asyncio
from Config.settings import Config
from core.context import AccountContext, AccountCache, AccountPaths
from core.dispatcher import install as install_dispatcher
from core.logger import setup_logger, account_logger
from core.client import VectorClient
from core.module_health import ModuleHealth
from database.connection import AccountDatabase
from database.migrations import run_for as run_migrations
from .state import BotState
from .health import HealthMonitor
from .watchdog import Watchdog
from .recovery import Recovery
from .errors import ErrorHandler

logger = setup_logger("VECTOR.runtime")


class Runtime:
    def __init__(self, account_id: str, manager):
        self.account_id = account_id
        self.manager = manager
        self.registry = manager.registry
        self.log = account_logger(account_id, "runtime")

        self.paths = AccountPaths(account_id, Config.ACCOUNTS_DIR)
        self.state = BotState()
        self.db = AccountDatabase(account_id, self.paths.database)
        self.cache = AccountCache(default_ttl=3600)

        self.client = VectorClient(
            account_id, self.paths,
            session_string=self._session_string(),
            phone=self._phone(),
        )

        self.errors = ErrorHandler(max_errors=100)
        self.module_health = ModuleHealth(account_id, threshold=5, window=60)

        self.ctx = AccountContext(
            account_id=account_id, client=self.client,
            paths=self.paths, database=self.db, cache=self.cache,
            state=self.state, registry=self.registry,
            config=Config, manager=manager,
            errors=self.errors, module_health=self.module_health,
        )

        self.client.ctx = self.ctx
        try:
            self.client.client.ctx = self.ctx
        except Exception:
            pass

        self.health = HealthMonitor(self)
        self.watchdog = Watchdog(self)
        self.recovery = Recovery(self)
        self._stopped = False
        self._watchdog_task = None

    def _session_string(self):
        from Config.environment import Environment
        return Environment.session_string_for(self.account_id)

    def _phone(self):
        from Config.environment import Environment
        return Environment.phone_for(self.account_id)

    async def initialize(self):
        self.log.info("running migrations…")
        await run_migrations(self.db)
        self.log.info("starting Telegram client…")
        await self.client.start()
        install_dispatcher(self.client.client, self.ctx)

    async def start(self):
        self.state.start()
        self.log.info("▶️ running")
        self._watchdog_task = asyncio.create_task(self.watchdog.start())

    async def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self.state.stop()

        for task in list(self.ctx.meta.get("background_tasks", [])):
            self._cancel_task(task)
        self.ctx.meta["background_tasks"] = []

        for tasks in self.ctx.meta.get("module_tasks", {}).values():
            for task in list(tasks):
                self._cancel_task(task)
        self.ctx.meta["module_tasks"] = {}

        try:
            self.watchdog.stop()
        except Exception:
            pass

        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._watchdog_task = None

        try:
            await self.client.stop()
        finally:
            try:
                await self.db.dispose()
            except Exception:
                pass
        self.log.info("⏹ stopped")

    @staticmethod
    def _cancel_task(task) -> None:
        if task is None or not isinstance(task, asyncio.Task):
            return
        if task.done():
            return
        try:
            task.cancel()
        except Exception:
            pass
