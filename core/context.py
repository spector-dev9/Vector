"""AccountContext — the isolation boundary."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


class AccountPaths:
    __slots__ = ("account_id", "root", "_cache", "_files")

    def __init__(self, account_id: str, base: Path):
        self.account_id = account_id
        self.root = base / account_id
        self._cache = self.root / "cache"
        self._files = self.root / "files"
        self.ensure()

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache.mkdir(exist_ok=True)
        self._files.mkdir(exist_ok=True)

    @property
    def database(self) -> Path:
        return self.root / "database.db"

    @property
    def session(self) -> Path:
        return self.root / "session"

    @property
    def cache(self) -> Path:
        return self._cache

    @property
    def files(self) -> Path:
        return self._files

    @staticmethod
    def _sanitize(name: str) -> str:
        safe = (name or "").replace("/", "_").replace("\\", "_").lstrip(".")
        safe = safe.replace("\x00", "")
        return safe or "_"

    def file(self, name: str) -> Path:
        return self._files / self._sanitize(name)

    def sub(self, name: str) -> Path:
        safe = self._sanitize(name)
        p = (self._files / safe).resolve()
        try:
            p.relative_to(self._files.resolve())
        except ValueError:
            p = self._files / "_"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def __repr__(self) -> str:
        return f"<AccountPaths {self.account_id} @ {self.root}>"


class AccountCache:
    __slots__ = ("_data", "default_ttl")

    def __init__(self, default_ttl: int = 3600):
        self._data: dict[str, tuple[Any, float]] = {}
        self.default_ttl = default_ttl

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        t = self.default_ttl if ttl is None else ttl
        self._data[key] = (value, time.time() + t)

    def get(self, key: str, default: Any = None) -> Any:
        item = self._data.get(key)
        if item is None:
            return default
        val, exp = item
        if time.time() > exp:
            self._data.pop(key, None)
            return default
        return val

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


@dataclass
class AccountContext:
    account_id: str
    client: Any
    paths: AccountPaths
    database: Any
    cache: AccountCache
    state: Any
    registry: Any
    config: Any = None
    manager: Any = None
    errors: Any = None
    module_health: Any = None
    meta: dict = field(default_factory=dict)

    @property
    def log_tag(self) -> str:
        return f"[{self.account_id}]"

    @property
    def sudo_users(self) -> list[int]:
        return self.config.SUDO_USERS if self.config else []

    def is_sudo(self, user_id: int) -> bool:
        s = self.sudo_users
        if not s:
            return False
        return user_id in s

    def __repr__(self) -> str:
        return f"<AccountContext {self.account_id}>"
