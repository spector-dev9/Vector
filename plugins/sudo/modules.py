"""Module manager — install, unload, reload, backup, restore, delete.

Backups are sent to Saved Messages only. Nothing is written to disk
under data/. Every backup is retrievable by replying to it.
"""
import io
import re
import time
from pathlib import Path

from core.decorators import command
from core.logger import setup_logger
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY, Formatters

META = ModuleMeta(
    name="modules", category="sudo",
    description="Full module lifecycle management from Telegram.",
    permission="sudo",
)

logger = setup_logger("VECTOR.modmanager")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PLUGINS_DIR = PROJECT_ROOT / "plugins"

_ALLOWED_CATEGORIES = {
    "root", "sudo", "account", "telegram", "moderation",
    "automation", "media", "tools", "developer", "fun", "system",
}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")

# marker that goes in every backup caption — used for search
MODULE_BACKUP_TAG = "#vector_module_backup"


# ═══════════════════════════════════════════════════════════════════
#  backup to Saved Messages
# ═══════════════════════════════════════════════════════════════════

async def _backup_saved(client, path: Path, reason: str = "") -> str | None:
    """Send a plugin file to Saved Messages with a searchable caption.

    Returns the message id as a string, or None on failure.
    """
    if not path.exists() or not path.is_file():
        return None
    try:
        raw = path.read_bytes()
    except Exception as e:
        logger.warning(f"backup read failed for {path}: {e}")
        return None

    rel = ""
    try:
        rel = str(path.relative_to(PROJECT_ROOT))
    except Exception:
        rel = path.name

    buf = io.BytesIO(raw)
    buf.name = path.name
    caption = (
        f"{MODULE_BACKUP_TAG}\n"
        f"🗂 **VECTOR module backup**\n"
        f"**Path:** `{rel}`\n"
        f"**Size:** {Formatters.format_size(len(raw))}\n"
        f"**When:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**Reason:** {reason or 'manual'}\n"
        f"\n_Restore: reply to this file with `.modrestore <category>`_"
    )
    try:
        sent = await client.send_file(
            "me", buf,
            caption=caption,
            force_document=True,
        )
        return str(sent.id)
    except Exception as e:
        logger.warning(f"backup send failed for {path}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
#  list / inspect
# ═══════════════════════════════════════════════════════════════════

@command("modlist", "List every module with disk + enabled state", permission="sudo")
async def modlist(event):
    modules = event.ctx.manager.list_modules()
    if not modules:
        await event.edit(Messages.info("No modules loaded."))
        return
    by_cat: dict = {}
    for key, info in modules.items():
        by_cat.setdefault(info.category, []).append((key, info))
    enabled = sum(1 for m in modules.values() if m.enabled)
    lines = [
        f"📦 **MODULES** — {len(modules)} total",
        f"✅ enabled: **{enabled}** · ⏸ disabled: **{len(modules) - enabled}**",
        SEP_FANCY,
    ]
    for cat in sorted(by_cat):
        lines.append(f"\n**{cat.upper()}** · {len(by_cat[cat])}")
        for key, info in sorted(by_cat[cat]):
            mark = "✅" if info.enabled else "⏸"
            disk = Path(info.path)
            d = "✓" if disk.exists() else "✗"
            lines.append(
                f"  {mark} {d} `{info.name}` · "
                f"{len(info.handlers)}h · {info.meta.permission}"
            )
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n_…truncated_"
    await event.edit(text)


@command(r"modinfo (?P<name>\w+)", "Show full metadata for a module", permission="sudo")
async def modinfo(event):
    key = event.ctx.manager.resolve_module_key(event.pattern_match.group("name"))
    if key is None:
        await event.edit(Messages.error("Not loaded."))
        return
    info = event.ctx.manager.get_module(key)
    disk = Path(info.path)
    p = info.meta
    lines = [
        f"📋 **{info.name}**",
        SEP_FANCY,
        f"**Category**   `{p.category}`",
        f"**Module key** `{p.key}`",
        f"**Permission** `{p.permission}`",
        f"**Version**    `{p.version}`",
        f"**Enabled**    {'✅ yes' if info.enabled else '⏸ no'}",
        f"**Handlers**   `{len(info.handlers)}`",
        f"**Disk**       {'✓ present' if disk.exists() else '✗ missing'}",
        f"**Path**       `{disk.relative_to(PROJECT_ROOT)}`",
        SEP_FANCY,
        f"_{p.description or 'no description'}_",
    ]
    if info.handlers:
        lines.append(f"\n**Handlers:** {', '.join(info.handlers[:15])}")
    await event.edit("\n".join(lines))


@command(r"modfind (?P<q>.+)", "Search modules by name/description", permission="sudo")
async def modfind(event):
    q = event.pattern_match.group("q").strip().lower()
    modules = event.ctx.manager.list_modules()
    matches = [m for m in modules.values()
               if q in m.name.lower() or q in m.meta.description.lower()]
    if not matches:
        await event.edit(Messages.info(f"No matches for `{q}`."))
        return
    lines = [f"🔍 **{len(matches)} module(s)**", SEP_FANCY]
    for info in sorted(matches, key=lambda m: m.name):
        mark = "✅" if info.enabled else "⏸"
        lines.append(f"{mark} `{info.meta.key}` — _{info.meta.description[:60]}_")
    await event.edit("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════
#  install
# ═══════════════════════════════════════════════════════════════════

@command(r"modload(?: (?P<cat>\w+))?", "Install a .py plugin from Telegram reply",
         permission="sudo")
async def modload(event):
    if not event.is_reply:
        await event.edit(Messages.error("Reply to a `.py` file."))
        return
    replied = await event.get_reply_message()
    if not replied or not replied.document:
        await event.edit(Messages.error("Replied message has no file."))
        return

    fname = None
    for a in getattr(replied.document, "attributes", []) or []:
        n = getattr(a, "file_name", None)
        if n:
            fname = n
            break
    if not fname or not fname.endswith(".py"):
        await event.edit(Messages.error("Only `.py` files accepted."))
        return

    stem = Path(fname).stem.lower()
    if not _NAME_RE.match(stem):
        await event.edit(Messages.error(f"Invalid module name `{stem}`."))
        return

    category = (event.pattern_match.group("cat") or "developer").lower()
    if category not in _ALLOWED_CATEGORIES:
        await event.edit(Messages.error(
            f"Unknown category `{category}`.\n"
            f"Allowed: {', '.join(sorted(_ALLOWED_CATEGORIES))}"))
        return

    await event.edit(Messages.loading(f"Downloading `{fname}`…"))

    buf = io.BytesIO()
    try:
        await event.client.download_media(replied, file=buf)
        buf.seek(0)
        source = buf.read().decode("utf-8")
    except UnicodeDecodeError:
        await event.edit(Messages.error("File is not valid UTF-8."))
        return
    except Exception as e:
        await event.edit(Messages.error(f"Download failed: {e}"))
        return

    target = PLUGINS_DIR / category / f"{stem}.py"

    # if the file already exists, back it up to Saved Messages first
    backup_ok = None
    if target.exists():
        backup_ok = await _backup_saved(
            event.client, target,
            reason=f"overwrite via .modload",
        )

    await event.edit(Messages.loading(f"Loading `{category}.{stem}`…"))

    count = await event.ctx.manager.install_module(category, stem, source)

    if count == 0:
        lines = [
            f"❌ **`{category}.{stem}` install failed**",
            SEP_FANCY,
            "Check the log for the traceback.",
        ]
        if backup_ok:
            lines.append(f"Previous version: Saved Messages (msg `{backup_ok}`)")
        await event.edit("\n".join(lines))
        return

    lines = [
        f"✅ **`{category}.{stem}` installed**",
        SEP_FANCY,
        f"File: `plugins/{category}/{stem}.py`",
        f"Handlers: **{count}**",
    ]
    if backup_ok:
        lines.append(f"Previous version: Saved Messages (msg `{backup_ok}`)")
    await event.edit("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════
#  enable / disable
# ═══════════════════════════════════════════════════════════════════

@command(r"modunload (?P<name>\w+)", "Disable a module (keep file)", permission="sudo")
async def modunload(event):
    name = event.pattern_match.group("name")
    key = event.ctx.manager.resolve_module_key(name)
    if key is None:
        await event.edit(Messages.error(f"`{name}` not loaded."))
        return
    ok = await event.ctx.manager.disable_module(key)
    if ok:
        await event.edit(Messages.success(
            f"Disabled `{name}`.\n_Re-enable with `.modactivate {name}`._"))
    else:
        await event.edit(Messages.info(f"`{name}` was already disabled."))


@command(r"moddeactivate (?P<name>\w+)", "Alias for .modunload", permission="sudo")
async def moddeactivate(event):
    await modunload(event)


@command(r"modactivate (?P<name>\w+)", "Re-enable a disabled module", permission="sudo")
async def modactivate(event):
    name = event.pattern_match.group("name")
    key = event.ctx.manager.resolve_module_key(name)
    if key is None:
        await event.edit(Messages.error(f"`{name}` not loaded."))
        return
    ok = await event.ctx.manager.enable_module(key)
    if ok:
        info = event.ctx.manager.get_module(key)
        await event.edit(Messages.success(
            f"Activated `{name}` — {len(info.handlers)} handler(s) attached."))
    else:
        await event.edit(Messages.info(f"`{name}` was already active."))


# ═══════════════════════════════════════════════════════════════════
#  reload
# ═══════════════════════════════════════════════════════════════════

@command(r"modreload (?P<name>\w+)", "Reload a module from disk", permission="sudo")
async def modreload(event):
    name = event.pattern_match.group("name")
    key = event.ctx.manager.resolve_module_key(name)
    if key is None:
        await event.edit(Messages.error(f"`{name}` not loaded."))
        return
    await event.edit(Messages.loading(f"Reloading `{name}`…"))
    count = await event.ctx.manager.reload_module(key)
    if count == 0:
        await event.edit(Messages.error(f"Reload of `{name}` failed."))
        return
    info = event.ctx.manager.get_module(key)
    state = "active" if (info and info.enabled) else "disabled"
    await event.edit(Messages.success(
        f"Reloaded `{name}` — {count} handler(s), state: {state}."))


@command("modreloadall", "Reload every module", permission="sudo")
async def modreloadall(event):
    await event.edit(Messages.loading("Reloading all modules…"))
    mods, handlers = await event.ctx.manager.reload_all()
    await event.edit(Messages.success(
        f"Reloaded **{mods}** module(s) · **{handlers}** handler(s)."))


@command("modscan", "Discover and load any new .py files on disk", permission="sudo")
async def modscan(event):
    await event.edit(Messages.loading("Scanning plugins/ for new modules…"))
    new = await event.ctx.manager.scan_new_modules()
    if not new:
        await event.edit(Messages.info("No new modules found."))
        return
    lines = [f"✅ **{len(new)} new module(s) loaded**", SEP_FANCY]
    for cat, name, count in new:
        lines.append(f"▸ `{cat}.{name}` · {count} handler(s)")
    await event.edit("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════
#  get / backup / list / restore
# ═══════════════════════════════════════════════════════════════════

@command(r"modget (?P<name>\w+)", "Send module's .py to Saved Messages",
         permission="sudo")
async def modget(event):
    name = event.pattern_match.group("name")
    key = event.ctx.manager.resolve_module_key(name)
    if key is None:
        await event.edit(Messages.error(f"`{name}` not loaded."))
        return
    path = event.ctx.manager.get_module_path(key)
    if path is None:
        await event.edit(Messages.error("File missing on disk."))
        return
    await event.edit(Messages.loading(f"Sending `{path.name}`…"))
    try:
        buf = io.BytesIO(path.read_bytes())
        buf.name = path.name
        await event.client.send_file(
            "me", buf,
            caption=f"📄 `{path.relative_to(PROJECT_ROOT)}`",
            force_document=True,
        )
    except Exception as e:
        await event.edit(Messages.error(f"Send failed: {e}"))
        return
    info = event.ctx.manager.get_module(key)
    await event.edit(Messages.success(
        f"Sent `{path.name}` to Saved Messages.\n"
        f"_Reply to it there with `.modload {info.category}` to reinstall._"))


@command(r"modexport (?P<name>\w+)", "Alias for .modget", permission="sudo")
async def modexport(event):
    await modget(event)


@command(r"modbackup (?P<name>\w+)", "Send a module backup to Saved Messages",
         permission="sudo")
async def modbackup(event):
    name = event.pattern_match.group("name")
    key = event.ctx.manager.resolve_module_key(name)
    if key is None:
        await event.edit(Messages.error(f"`{name}` not loaded."))
        return
    path = event.ctx.manager.get_module_path(key)
    if path is None:
        await event.edit(Messages.error("File missing on disk."))
        return
    await event.edit(Messages.loading(f"Backing up `{name}`…"))
    msg_id = await _backup_saved(event.client, path, reason="manual backup")
    if msg_id is None:
        await event.edit(Messages.error("Backup failed."))
        return
    await event.edit(Messages.success(
        f"Backup of `{name}` sent to Saved Messages.\n"
        f"_Msg id: `{msg_id}`_"))


@command("modbackups", "List recent module backups in Saved Messages",
         permission="sudo")
async def modbackups(event):
    await event.edit(Messages.loading("Searching Saved Messages…"))
    try:
        msgs = await event.client.get_messages(
            "me", search=MODULE_BACKUP_TAG, limit=50,
        )
    except Exception as e:
        await event.edit(Messages.error(f"Search failed: {e}"))
        return
    if not msgs:
        await event.edit(Messages.info(
            "No module backups found in Saved Messages."))
        return

    lines = [f"🗂 **{len(msgs)} module backup(s)**", SEP_FANCY]
    for m in msgs[:25]:
        fname = "?"
        try:
            if m.document:
                for a in m.document.attributes or []:
                    n = getattr(a, "file_name", None)
                    if n:
                        fname = n
                        break
        except Exception:
            pass
        when = m.date.strftime("%Y-%m-%d %H:%M") if m.date else "?"
        lines.append(f"▸ `{fname}` · {when} · msg `{m.id}`")
    if len(msgs) > 25:
        lines.append(f"_…+{len(msgs)-25} more_")
    lines.append(
        "\n_Restore: reply to the backup file in Saved Messages with "
        "`.modrestore <category>`_"
    )
    await event.edit("\n".join(lines))


@command(r"modrestore(?: (?P<cat>\w+))?", "Restore a module from a Saved Messages backup",
         permission="sudo")
async def modrestore(event):
    """Reply to a backup file in Saved Messages. Optionally pass category."""
    if not event.is_reply:
        await event.edit(Messages.error(
            "Reply to a backup file in Saved Messages.\n"
            "_(Open Saved Messages, find the backup, reply to it)_"))
        return

    replied = await event.get_reply_message()
    if not replied or not replied.document:
        await event.edit(Messages.error("Replied message has no file."))
        return

    fname = None
    for a in getattr(replied.document, "attributes", []) or []:
        n = getattr(a, "file_name", None)
        if n:
            fname = n
            break
    if not fname or not fname.endswith(".py"):
        await event.edit(Messages.error("Only `.py` files accepted."))
        return

    stem = Path(fname).stem.lower()
    if not _NAME_RE.match(stem):
        await event.edit(Messages.error(f"Invalid module name `{stem}`."))
        return

    category = (event.pattern_match.group("cat") or "developer").lower()
    if category not in _ALLOWED_CATEGORIES:
        await event.edit(Messages.error(
            f"Unknown category `{category}`.\n"
            f"Allowed: {', '.join(sorted(_ALLOWED_CATEGORIES))}"))
        return

    await event.edit(Messages.loading(f"Downloading `{fname}`…"))

    buf = io.BytesIO()
    try:
        await event.client.download_media(replied, file=buf)
        buf.seek(0)
        source = buf.read().decode("utf-8")
    except Exception as e:
        await event.edit(Messages.error(f"Download failed: {e}"))
        return

    target = PLUGINS_DIR / category / f"{stem}.py"

    # back up current version to Saved Messages if it exists
    if target.exists():
        await _backup_saved(
            event.client, target,
            reason=f"overwrite via .modrestore of {fname}",
        )

    await event.edit(Messages.loading(f"Loading `{category}.{stem}`…"))

    count = await event.ctx.manager.install_module(category, stem, source)

    if count == 0:
        await event.edit(Messages.error(
            f"Restored `{fname}` to disk but failed to load. Check log."))
        return

    await event.edit(Messages.success(
        f"Restored `{category}.{stem}` — {count} handler(s)."))


# ═══════════════════════════════════════════════════════════════════
#  delete
# ═══════════════════════════════════════════════════════════════════

@command(r"moddel (?P<name>\w+)", "Backup to Saved Messages and delete a module",
         permission="sudo")
async def moddel(event):
    name = event.pattern_match.group("name")
    key = event.ctx.manager.resolve_module_key(name)
    if key is None:
        await event.edit(Messages.error(f"`{name}` not loaded."))
        return
    path = event.ctx.manager.get_module_path(key)
    if path is None:
        await event.edit(Messages.error("File missing on disk."))
        return

    await event.edit(Messages.loading(f"Backing up `{name}`…"))
    msg_id = await _backup_saved(event.client, path, reason=f"delete via .moddel")

    if msg_id is None:
        await event.edit(Messages.error(
            "Backup to Saved Messages failed. File NOT deleted."))
        return

    ok = await event.ctx.manager.delete_module(key)
    if not ok:
        await event.edit(Messages.warning(
            f"Backed up (msg `{msg_id}`) but delete failed."))
        return

    await event.edit(Messages.success(
        f"`{name}` backed up and deleted.\n"
        f"Backup msg: `{msg_id}` in Saved Messages.\n"
        f"_Restore: reply to the backup with `.modrestore <category>`_"))


# ═══════════════════════════════════════════════════════════════════
#  help
# ═══════════════════════════════════════════════════════════════════

@command("modhelp", "Full module manager help")
async def modhelp(event):
    await event.edit(
        "🧩 **MODULE MANAGER**\n"
        f"{SEP_FANCY}\n\n"
        "**List / inspect:**\n"
        "▸ `.modlist` — every module + state\n"
        "▸ `.modinfo <name>` — full metadata\n"
        "▸ `.modfind <query>` — search\n\n"
        "**Install:**\n"
        "▸ `.modload [cat]` — reply to a `.py` file\n"
        "▸ `.modscan` — load any new .py files on disk\n\n"
        "**Enable / disable:**\n"
        "▸ `.modunload <name>` — detach, keep file\n"
        "▸ `.modactivate <name>` — reattach\n\n"
        "**Reload:**\n"
        "▸ `.modreload <name>`\n"
        "▸ `.modreloadall`\n\n"
        "**Backup (Saved Messages only, no disk):**\n"
        "▸ `.modbackup <name>` — send current file to Saved\n"
        "▸ `.modbackups` — list backups in Saved\n"
        "▸ `.modrestore [cat]` — reply to a backup to restore\n"
        "▸ `.modget <name>` — send current file to Saved\n"
        "▸ `.moddel <name>` — backup + delete\n\n"
        f"{SEP_FANCY}\n"
        "**Categories:** root, sudo, account, telegram, moderation, "
        "automation, media, tools, developer, fun, system\n"
        "Default: `developer`."
    )