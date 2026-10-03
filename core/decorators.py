"""Decorators for VECTOR plugins."""
from __future__ import annotations
import inspect
import re
from functools import wraps
from typing import Optional

from Config.settings import Config
from core.logger import setup_logger

logger = setup_logger("VECTOR.decorators")

_CMD_NAME_RE = re.compile(r"^([a-zA-Z0-9_]+)")


def _anchor(pattern: str) -> str:
    """Append (?!\\w) after the leading command name so .pingfoo
    does not match .ping — only .ping followed by a non-word char."""
    m = re.match(r"([a-zA-Z0-9_]+)(.*)", pattern, re.DOTALL)
    if not m:
        return pattern
    name, rest = m.group(1), m.group(2)
    return f"{name}(?!\\w){rest}"


def _extract_cmd_name(pattern: str) -> str:
    m = _CMD_NAME_RE.match(pattern or "")
    return m.group(1) if m else (pattern or "")


def _compile_pattern(pattern: str) -> "re.Pattern":
    """Build the compiled regex for a command pattern.

    Prefix is escaped, command name is anchored, and case-insensitivity
    is set as a compiled flag — not via inline (?i), which some
    Telethon versions strip when they recompile the pattern internally.
    """
    escaped_prefix = re.escape(Config.CMD_PREFIX)
    source = f"^{escaped_prefix}{_anchor(pattern)}"
    return re.compile(source, re.IGNORECASE)


def _resolve_ctx(event):
    try:
        c = event.ctx
        if c is not None:
            return c
    except Exception:
        pass
    client = getattr(event, "client", None)
    if client is not None:
        return getattr(client, "ctx", None)
    return None


def _is_sudo(ctx, event) -> bool:
    if ctx is None:
        return False
    return ctx.is_sudo(event.sender_id)


def _record_error(ctx, err: BaseException, context: str) -> None:
    if ctx is None:
        return
    h = getattr(ctx, "errors", None)
    if h is not None:
        try:
            h.log_error(err, context=context)
        except Exception:
            pass
    mh = getattr(ctx, "module_health", None)
    if mh is not None:
        try:
            if mh.record_failure(context):
                logger.warning(
                    f"{ctx.log_tag} auto-disabled `{context}` "
                    f"after repeated failures"
                )
        except Exception:
            pass


def _is_handler_disabled(ctx, name: str) -> bool:
    if ctx is None:
        return False
    mh = getattr(ctx, "module_health", None)
    if mh is None:
        return False
    try:
        return mh.is_disabled(name)
    except Exception:
        return False


async def _typing_then(func, event, action):
    from helpers.formatting.animator import typing
    async with typing(event.client, event.chat_id, action):
        await func(event)


def command(
    pattern: str,
    description: str = "",
    *,
    category: Optional[str] = None,
    permission: str = "user",
    action: str = "typing",
    version: str = "1.0.0",
    tags: tuple = (),
):
    def decorator(func):
        raw_sudo = getattr(func, "_sudo_only", False)
        raw_root = getattr(func, "_root_only", False)
        final_permission = permission
        if raw_root and permission == "user":
            final_permission = "root"
        elif raw_sudo and permission == "user":
            final_permission = "sudo"

        @wraps(func)
        async def wrapper(event):
            ctx = _resolve_ctx(event)

            if _is_handler_disabled(ctx, func.__name__):
                return

            if final_permission == "sudo" and not _is_sudo(ctx, event):
                try:
                    await event.reply("⛔ **Access denied** — sudo users only.")
                except Exception:
                    pass
                return
            if final_permission == "root":
                if not _is_sudo(ctx, event):
                    try:
                        await event.reply("⛔ **Access denied** — root users only.")
                    except Exception:
                        pass
                    return
                if ctx and not ctx.meta.get("root_unlocked", False):
                    try:
                        await event.reply(
                            "🔒 **Root locked.** Send `.root unlock` first."
                        )
                    except Exception:
                        pass
                    return

            if ctx and hasattr(ctx.state, "increment_commands"):
                ctx.state.increment_commands()

            try:
                await _typing_then(func, event, action)
            except Exception as e:
                if ctx and hasattr(ctx.state, "increment_errors"):
                    ctx.state.increment_errors()
                tag = ctx.log_tag if ctx else "[?]"
                logger.error(f"{tag} {func.__name__}: {e}", exc_info=True)
                _record_error(ctx, e, func.__name__)
                try:
                    from utils.messages import Messages
                    await event.reply(Messages.error(str(e)))
                except Exception:
                    pass

        wrapper._is_handler = True
        wrapper._raw_pattern = pattern
        wrapper._pattern = _compile_pattern(pattern)
        wrapper._description = description
        wrapper._command_name = _extract_cmd_name(pattern)
        wrapper._docstring = inspect.getdoc(func) or ""
        wrapper._category = category
        wrapper._permission = final_permission
        wrapper._version = version
        wrapper._tags = tags
        wrapper._sudo_only = final_permission in ("sudo", "root")
        return wrapper

    return decorator


def sudo_only(func):
    func._sudo_only = True
    return func


def root_only(func):
    func._root_only = True
    return func


def listener(event_builder):
    def decorator(func):
        @wraps(func)
        async def wrapper(event):
            try:
                await func(event)
            except Exception as e:
                ctx = _resolve_ctx(event)
                tag = ctx.log_tag if ctx else "[?]"
                logger.error(f"{tag} listener {func.__name__}: {e}", exc_info=True)
                _record_error(ctx, e, f"listener:{func.__name__}")

        wrapper._is_listener = True
        wrapper._event_builder = event_builder
        wrapper._docstring = inspect.getdoc(func) or ""
        return wrapper

    return decorator