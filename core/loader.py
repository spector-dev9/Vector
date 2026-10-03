"""Plugin discovery."""
from __future__ import annotations
import importlib
import inspect
import re
import sys
from pathlib import Path
from typing import Iterable

from core.logger import setup_logger

logger = setup_logger("VECTOR.loader")

_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class PluginLoader:
    def __init__(self, plugins_dir: Path):
        self.plugins_dir = plugins_dir

    def categories(self):
        if not self.plugins_dir.exists():
            return []
        return sorted(
            p for p in self.plugins_dir.iterdir()
            if p.is_dir() and not p.name.startswith("_")
        )

    def modules_in(self, category_dir: Path):
        return sorted(
            f for f in category_dir.glob("*.py")
            if not f.name.startswith("_")
        )

    def load_one(self, category: str, module_path: Path):
        importlib.invalidate_caches()
        dotted = f"plugins.{category}.{module_path.stem}"
        module = importlib.import_module(dotted)
        handlers, listeners = [], []
        for name, obj in inspect.getmembers(module):
            if not callable(obj):
                continue
            if getattr(obj, "_is_handler", False):
                handlers.append((name, obj))
            elif getattr(obj, "_is_listener", False):
                listeners.append((name, obj))
        return module, handlers, listeners

    def iter_all(self) -> Iterable[tuple]:
        for cat_dir in self.categories():
            if not _CATEGORY_RE.match(cat_dir.name):
                logger.warning(f"skip malformed category dir: {cat_dir.name}")
                continue
            for mod_path in self.modules_in(cat_dir):
                yield cat_dir.name, mod_path.stem, mod_path

    def forget(self, category: str, module_name: str) -> None:
        sys.modules.pop(f"plugins.{category}.{module_name}", None)
