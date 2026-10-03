"""VectorManager — owns every AccountContext and every loaded module.

═══════════════════════════════════════════════════════════════════════
PUBLIC API — everything a plugin could ever need. No core edits required.
═══════════════════════════════════════════════════════════════════════

Lifecycle (called by main.py only):
    manager.load_plugins()                    → (modules, handlers)
    await manager.attach_account(ctx)         → register handlers for one account
    await manager.stop_all()                  → tear down every account

Module operations (safe to call from any plugin):
    await manager.load_module(category, name)              # from disk
    await manager.install_module(category, name, source)   # from string
    await manager.unload_module(key)                       # detach + forget
    await manager.disable_module(key)                      # detach, keep registered
    await manager.enable_module(key)                       # reattach
    await manager.reload_module(key)                       # reload from disk
    await manager.reload_all()                             # every loaded module
    await manager.scan_new_modules()                       # discover + load new files
    await manager.delete_module(key)                       # unload + delete file

Inspection (sync — no account iteration):
    manager.resolve_module_key(name)         → key or None
    manager.get_module(key)                  → ModuleInfo or None
    manager.list_modules()                   → dict[str, ModuleInfo]
    manager.module_pairs(key)                → [(callback, builder)]
    manager.get_module_path(key)             → Path or None
    manager.registry.get_stats()             → totals dict

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import asyncio
import inspect
from pathlib import Path
from typing import Callable, Optional

from telethon import events

from core.context import AccountContext
from core.loader import PluginLoader
from core.logger import setup_logger
from core.module import ModuleInfo, ModuleMeta

logger = setup_logger("VECTOR.manager")


# ─────────────────────────────────────────────────────────────────────
#  startup-hook normalization (private)
# ─────────────────────────────────────────────────────────────────────

async def _normalize_hook_result(
    result,
    log_tag: str,
    key: str,
    *,
    hook_is_async: bool = False,
) -> Optional[asyncio.Task]:
    """Coerce a startup-hook return into an asyncio.Task or None.

    Contract for on_startup(ctx):
        async  → Task            tracked
        async  → None            ignored
        async  → coroutine       scheduled / tracked
        async  → awaitable       scheduled / tracked
        sync   → Task            tracked
        sync   → coroutine       scheduled / tracked
        sync   → awaitable       scheduled / tracked
        either → other value     logged / ignored
    """
    try:
        if hook_is_async and asyncio.iscoroutine(result):
            result = await result

        if isinstance(result, asyncio.Task):
            return result

        if asyncio.iscoroutine(result):
            return asyncio.create_task(result)

        if inspect.isawaitable(result):
            try:
                return asyncio.ensure_future(result)
            except Exception as e:
                logger.warning(
                    f"{log_tag} hook {key} returned unschedulable awaitable "
                    f"({type(result).__name__}): {e}"
                )
                return None

        if result is None:
            return None

        logger.warning(
            f"{log_tag} hook {key} returned non-awaitable "
            f"{type(result).__name__} — ignored"
        )
        return None

    except Exception as e:
        logger.error(
            f"{log_tag} hook {key} execution failed: {e}",
            exc_info=True,
        )
        return None


def _cancel_task(task) -> None:
    """Cancel an asyncio.Task if it's live; ignore anything else."""
    if task is None:
        return
    if not isinstance(task, asyncio.Task):
        return
    if task.done():
        return
    try:
        task.cancel()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────
#  ModuleRegistry — pure state. Never talks to accounts.
# ─────────────────────────────────────────────────────────────────────

class ModuleRegistry:
    def __init__(self, plugins_dir: Path):
        self.modules: dict[str, ModuleInfo] = {}
        self.commands: dict[str, dict] = {}
        self._handlers_by_module: dict[str, list] = {}
        self._startup_hooks: dict[str, Callable] = {}
        self._loader = PluginLoader(plugins_dir)
        self.plugins_dir = plugins_dir

    # ── load ──────────────────────────────────────────────────────────

    def load_all(self):
        total_mods = total_handlers = 0
        for category, name, path in self._loader.iter_all():
            count = self._load(category, name, path)
            if count:
                total_mods += 1
                total_handlers += count
        logger.info(
            f"✅ Loaded {total_handlers} handler(s) "
            f"from {total_mods} module(s) across "
            f"{len(self.get_all_categories())} categor(y|ies)"
        )
        return total_mods, total_handlers

    def _load(self, category: str, name: str, path: Path) -> int:
        try:
            module, handlers, listeners = self._loader.load_one(category, path)
        except Exception as e:
            logger.error(f"❌ {category}/{name}: {e}", exc_info=True)
            return 0

        meta = getattr(module, "META", None)
        if not isinstance(meta, ModuleMeta):
            meta = ModuleMeta(
                name=name, category=category,
                description=(getattr(module, "__doc__", "") or "").strip().split("\n")[0],
                permission="user",
            )
        info = ModuleInfo(meta=meta, path=str(path))

        count = 0
        for handler_name, handler in handlers:
            builder = events.NewMessage(pattern=handler._pattern, outgoing=True)
            self._register(info, handler, builder)
            info.add_handler(handler_name)
            cmd = handler._command_name.lower()
            if cmd in self.commands:
                logger.warning(
                    f"⚠️  command collision '{cmd}': "
                    f"{self.commands[cmd]['module']} vs {info.meta.key}"
                )
            self.commands[cmd] = {
                "name": handler._command_name,
                "pattern": handler._raw_pattern,
                "description": handler._description,
                "docstring": handler._docstring,
                "category": handler._category or category,
                "module": info.meta.key,
                "permission": getattr(handler, "_permission", "user"),
                "sudo_only": getattr(handler, "_sudo_only", False),
            }
            count += 1

        for handler_name, handler in listeners:
            self._register(info, handler, handler._event_builder)
            info.add_handler(handler_name)
            count += 1

        hook = getattr(module, "on_startup", None)
        if callable(hook):
            self._startup_hooks[info.meta.key] = hook

        if count:
            self.modules[info.meta.key] = info
        return count

    def _register(self, info: ModuleInfo, callback, builder):
        self._handlers_by_module.setdefault(info.meta.key, []).append(
            (callback, builder)
        )

    # ── unload ────────────────────────────────────────────────────────

    def unload(self, key: str) -> bool:
        """Remove a module's handlers, commands, and startup hook from the registry."""
        pairs = self._handlers_by_module.pop(key, [])
        for cmd_name in list(self.commands.keys()):
            if self.commands[cmd_name]["module"] == key:
                del self.commands[cmd_name]
        info = self.modules.pop(key, None)
        self._startup_hooks.pop(key, None)
        if info:
            self._loader.forget(info.category, info.name)
        return info is not None and bool(pairs or True)

    # ── inspection ────────────────────────────────────────────────────

    def resolve_module_key(self, name: str):
        if name in self.modules:
            return name
        matches = [k for k, info in self.modules.items() if info.name == name]
        return matches[0] if len(matches) == 1 else None

    def module_pairs(self, key: str):
        return self._handlers_by_module.get(key, [])

    def get_stats(self):
        return {
            "total_modules": len(self.modules),
            "total_handlers": sum(len(m.handlers) for m in self.modules.values()),
            "total_commands": len(self.commands),
            "categories": len(self.get_all_categories()),
        }

    def get_all_categories(self):
        return sorted({m.meta.category for m in self.modules.values()})

    def get_commands_by_category(self, category=None):
        out = {}
        for info in self.commands.values():
            cat = info["category"]
            if category and cat.lower() != category.lower():
                continue
            out.setdefault(cat, []).append(info)
        for c in out:
            out[c].sort(key=lambda x: x["name"])
        return out

    def get_command_info(self, name):
        return self.commands.get(name.lower())

    def search_commands(self, query):
        q = query.lower()
        return [
            c for c in self.commands.values()
            if q in c["name"].lower() or q in c["description"].lower()
        ]


# ─────────────────────────────────────────────────────────────────────
#  VectorManager — owns accounts + coordinates registry
# ─────────────────────────────────────────────────────────────────────

class VectorManager:
    def __init__(self, plugins_dir: Optional[Path] = None):
        if plugins_dir is None:
            plugins_dir = Path(__file__).parent.parent / "plugins"
        self.registry = ModuleRegistry(Path(plugins_dir))
        self.accounts: dict[str, AccountContext] = {}
        self.plugins_dir = Path(plugins_dir)

    # ═════════════════════════════════════════════════════════════════
    #  LIFECYCLE  (called by main.py)
    # ═════════════════════════════════════════════════════════════════

    def load_plugins(self):
        return self.registry.load_all()

    async def attach_account(self, ctx: AccountContext):
        self.accounts[ctx.account_id] = ctx
        for module in self.registry.modules.values():
            if not module.enabled:
                continue
            for cb, builder in self.registry.module_pairs(module.meta.key):
                ctx.client.add_event_handler(cb, builder)
        logger.info(
            f"{ctx.log_tag} attached "
            f"{self.registry.get_stats()['total_handlers']} handler(s)"
        )

        executed = ctx.meta.setdefault("_executed_hooks", set())
        for key, hook in self.registry._startup_hooks.items():
            info = self.registry.modules.get(key)
            if info is None or not info.enabled:
                continue
            if key in executed:
                continue
            await self._run_hook(ctx, key, hook, executed)

    async def stop_all(self):
        for ctx in list(self.accounts.values()):
            try:
                await ctx.client.stop()
            except Exception as e:
                logger.warning(f"{ctx.log_tag} stop: {e}")
        self.accounts.clear()

    # ═════════════════════════════════════════════════════════════════
    #  MODULE OPERATIONS  (public — plugins call these)
    # ═════════════════════════════════════════════════════════════════

    async def load_module(self, category: str, name: str) -> int:
        """Load a module from disk. Attaches to every account + runs hook.

        If the module is already loaded, acts as reload.
        Returns the number of handlers registered (0 on failure).
        """
        path = self.plugins_dir / category / f"{name}.py"
        if not path.exists():
            logger.error(f"load_module: file not found at {path}")
            return 0

        key = f"{category}.{name}"
        if key in self.registry.modules:
            return await self.reload_module(key)

        count = self.registry._load(category, name, path)
        if count == 0:
            return 0

        await self._attach_key_to_accounts(key)

        hook = self.registry._startup_hooks.get(key)
        if hook is not None:
            for ctx in self.accounts.values():
                executed = ctx.meta.setdefault("_executed_hooks", set())
                await self._run_hook(ctx, key, hook, executed)

        return count

    async def install_module(self, category: str, name: str, source: str) -> int:
        """Write source to disk and load it. Used by .modload.

        Returns handler count. 0 on any failure (syntax, write, load).
        """
        try:
            compile(source, f"{name}.py", "exec")
        except SyntaxError as e:
            logger.error(
                f"install_module syntax error in {category}/{name}.py: "
                f"line {e.lineno}: {e.msg}"
            )
            return 0

        path = self.plugins_dir / category / f"{name}.py"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        except Exception as e:
            logger.error(f"install_module write failed for {path}: {e}")
            return 0

        return await self.load_module(category, name)

    async def unload_module(self, key: str) -> bool:
        """Detach handlers from every account + forget the module entirely.

        File stays on disk. To bring back you must reload/reinstall.
        """
        info = self.registry.modules.get(key)
        if info is None:
            return False

        await self._detach_key_from_accounts(key)
        self.registry.unload(key)
        logger.info(f"unloaded module {key}")
        return True

    async def disable_module(self, key: str) -> bool:
        """Detach handlers from every account, keep module registered as disabled.

        Reversible via enable_module(). File stays on disk.
        """
        info = self.registry.modules.get(key)
        if info is None or not info.enabled:
            return False

        await self._detach_key_from_accounts(key)
        info.disable()
        logger.info(f"disabled module {key}")
        return True

    async def enable_module(self, key: str) -> bool:
        """Reattach handlers to every account + re-run startup hook.

        Only works for modules that are registered but disabled.
        """
        info = self.registry.modules.get(key)
        if info is None or info.enabled:
            return False

        await self._attach_key_to_accounts(key)

        hook = self.registry._startup_hooks.get(key)
        if hook is not None:
            for ctx in self.accounts.values():
                executed = ctx.meta.setdefault("_executed_hooks", set())
                executed.discard(key)
                await self._run_hook(ctx, key, hook, executed)

        info.enable()
        logger.info(f"enabled module {key}")
        return True

    async def reload_module(self, key: str) -> int:
        """Re-import from disk, re-register, reattach. Preserves enabled state."""
        if key not in self.registry.modules:
            return 0
        info = self.registry.modules[key]
        was_enabled = info.enabled
        category, name = info.meta.category, info.meta.name
        path = Path(info.path)

        await self._detach_key_from_accounts(key)
        self.registry.unload(key)

        count = self.registry._load(category, name, path)

        new_info = self.registry.modules.get(key)
        if new_info is not None and was_enabled:
            await self._attach_key_to_accounts(key)
            hook = self.registry._startup_hooks.get(key)
            if hook is not None:
                for ctx in self.accounts.values():
                    executed = ctx.meta.setdefault("_executed_hooks", set())
                    executed.discard(key)
                    await self._run_hook(ctx, key, hook, executed)
        elif new_info is not None:
            new_info.disable()

        return count

    async def reload_all(self) -> tuple:
        """Reload every loaded module. Returns (modules, handlers) totals."""
        keys = list(self.registry.modules.keys())
        mods = handlers = 0
        for key in keys:
            count = await self.reload_module(key)
            if count:
                mods += 1
                handlers += count
        return mods, handlers

    async def scan_new_modules(self) -> list:
        """Discover .py files not yet loaded, load them.

        Returns list of (category, name, handler_count) for each newly loaded.
        """
        newly_loaded = []
        for category, name, path in self.registry._loader.iter_all():
            key = f"{category}.{name}"
            if key in self.registry.modules:
                continue
            count = await self.load_module(category, name)
            if count:
                newly_loaded.append((category, name, count))
        return newly_loaded

    async def delete_module(self, key: str) -> bool:
        """Unload + delete the .py file from disk."""
        info = self.registry.modules.get(key)
        path = Path(info.path) if info else None

        if info is not None:
            await self.unload_module(key)

        if path is None or not path.exists():
            return False

        try:
            path.unlink()
            return True
        except Exception as e:
            logger.error(f"delete_module file unlink failed for {path}: {e}")
            return False

    # ═════════════════════════════════════════════════════════════════
    #  INSPECTION  (sync — no account iteration)
    # ═════════════════════════════════════════════════════════════════

    def resolve_module_key(self, name: str):
        return self.registry.resolve_module_key(name)

    def get_module(self, key: str):
        return self.registry.modules.get(key)

    def list_modules(self):
        return dict(self.registry.modules)

    def module_pairs(self, key: str):
        return self.registry.module_pairs(key)

    def get_module_path(self, key: str):
        info = self.registry.modules.get(key)
        if info is None:
            return None
        p = Path(info.path)
        return p if p.exists() else None

    def get(self, account_id):
        return self.accounts.get(account_id)

    def all(self):
        return list(self.accounts.values())

    # ═════════════════════════════════════════════════════════════════
    #  PRIVATE HELPERS
    # ═════════════════════════════════════════════════════════════════

    async def _attach_key_to_accounts(self, key: str) -> None:
        """Attach a module's handlers to every live account."""
        pairs = self.registry.module_pairs(key)
        if not pairs:
            return
        for ctx in self.accounts.values():
            for cb, builder in pairs:
                try:
                    ctx.client.add_event_handler(cb, builder)
                except Exception as e:
                    logger.warning(
                        f"{ctx.log_tag} attach handler for {key}: {e}"
                    )

    async def _detach_key_from_accounts(self, key: str) -> None:
        """Detach a module's handlers from every live account + cancel tasks."""
        pairs = self.registry.module_pairs(key)
        for ctx in self.accounts.values():
            for cb, builder in pairs:
                try:
                    ctx.client.remove_event_handler(cb, builder)
                except Exception:
                    pass
            for task in ctx.meta.get("module_tasks", {}).pop(key, []):
                _cancel_task(task)

    async def _run_hook(self, ctx, key, hook, executed: set) -> None:
        """Run a single startup hook for one account."""
        try:
            raw = hook(ctx)
        except Exception as e:
            logger.error(f"{ctx.log_tag} hook {key} raised: {e}", exc_info=True)
            return
        task = await _normalize_hook_result(
            raw, ctx.log_tag, key,
            hook_is_async=inspect.iscoroutinefunction(hook),
        )
        if task is not None:
            ctx.meta.setdefault("module_tasks", {}).setdefault(key, []).append(task)
        executed.add(key)
        logger.info(f"{ctx.log_tag} startup hook ok: {key}")