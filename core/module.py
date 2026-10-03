"""Module metadata."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ModuleMeta:
    name: str
    category: str
    description: str = ""
    permission: str = "user"
    version: str = "1.0.0"
    tags: tuple = ()

    @property
    def key(self) -> str:
        return f"{self.category}.{self.name}"


@dataclass
class ModuleInfo:
    meta: ModuleMeta
    path: str
    handlers: list = field(default_factory=list)
    enabled: bool = True
    loaded_at: datetime = field(default_factory=datetime.now)
    error_count: int = 0

    def add_handler(self, name: str) -> None:
        self.handlers.append(name)

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def category(self) -> str:
        return self.meta.category

    def to_dict(self) -> dict:
        return {
            "name": self.meta.name,
            "category": self.meta.category,
            "description": self.meta.description,
            "permission": self.meta.permission,
            "version": self.meta.version,
            "tags": list(self.meta.tags),
            "handlers": self.handlers,
            "enabled": self.enabled,
            "loaded_at": self.loaded_at.isoformat(),
            "error_count": self.error_count,
        }

    def __repr__(self) -> str:
        return f"<Module {self.meta.key} handlers={len(self.handlers)}>"
