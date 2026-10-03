"""Project file access — push, read, list, delete.

Backups are sent to Saved Messages only. Nothing is written to disk
under data/. Every backup is retrievable by replying to it.
"""
import io
import time
from pathlib import Path

from core.decorators import command
from core.logger import setup_logger
from core.module import ModuleMeta
from Config.settings import Config
from utils import Messages, SEP_FANCY, Formatters

META = ModuleMeta(
    name="files", category="sudo",
    description="Push, read, list and delete project files.",
    permission="sudo",
)

logger = setup_logger("VECTOR.files")

ROOT = Path(Config.BASE_DIR)
PROTECTED = {".env", "session"}
PROTECTED_DIRS = {".git", "__pycache__", "data", "venv", ".venv", "env", "node_modules"}
ALLOWED_EXT = {".py", ".txt", ".md", ".json", ".yaml", ".yml", ".toml",
               ".ini", ".cfg", ".env", ".gitignore", ".html", ".css",
               ".js", ".sh", ".sql", ".xml", ".log", ".conf"}

FILE_BACKUP_TAG = "#vector_file_backup"


def _safe(user_input):
    user_input = (user_input or "").strip().lstrip("/")
    if not user_input:
        return None
    parts = Path(user_input).parts
    if ".." in parts:
        return None
    target = (ROOT / user_input).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        return None
    if any(p in PROTECTED_DIRS for p in target.relative_to(ROOT.resolve()).parts):
        return None
    if target.name in PROTECTED:
        return None
    return target


async def _backup_saved(client, target: Path, reason: str = "") -> str | None:
    """Send a file to Saved Messages with a searchable caption."""
    if not target.exists() or not target.is_file():
        return None
    try:
        raw = target.read_bytes()
    except Exception as e:
        logger.warning(f"backup read failed for {target}: {e}")
        return None

    rel = ""
    try:
        rel = str(target.relative_to(ROOT))
    except Exception:
        rel = target.name

    buf = io.BytesIO(raw)
    buf.name = target.name
    caption = (
        f"{FILE_BACKUP_TAG}\n"
        f"📄 **VECTOR file backup**\n"
        f"**Path:** `{rel}`\n"
        f"**Size:** {Formatters.format_size(len(raw))}\n"
        f"**When:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**Reason:** {reason or 'manual'}\n"
        f"\n_Restore: reply to this file with `.filrestore`_"
    )
    try:
        sent = await client.send_file(
            "me", buf,
            caption=caption,
            force_document=True,
        )
        return str(sent.id)
    except Exception as e:
        logger.warning(f"backup send failed for {target}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
#  pushfile / readfile / lsfile / rmfile2
# ═══════════════════════════════════════════════════════════════════

@command(r"pushfile(?:\s+(.+))?", "Overwrite a project file (reply)",
         permission="sudo")
async def pushfile(event):
    if not event.is_reply:
        await event.edit(Messages.error("Reply to a file."))
        return
    replied = await event.get_reply_message()
    if not replied.document:
        await event.edit(Messages.error("No file attached."))
        return
    fname = "uploaded.txt"
    for a in replied.document.attributes or []:
        if getattr(a, "file_name", None):
            fname = a.file_name
            break
    arg = (event.pattern_match.group(1) or "").strip() or fname
    target = _safe(arg)
    if target is None:
        await event.edit(Messages.error("Refused (unsafe path)."))
        return
    ext = target.suffix.lower()
    if ext and ext not in ALLOWED_EXT:
        await event.edit(Messages.error(f"Extension `{ext}` not allowed."))
        return

    await event.edit(Messages.loading(f"Downloading `{fname}`…"))
    buf = io.BytesIO()
    await event.client.download_media(replied, file=buf)
    buf.seek(0)
    raw = buf.read()

    # back up the existing file to Saved Messages BEFORE overwriting
    backup_msg_id = None
    existed = target.exists()
    if existed:
        backup_msg_id = await _backup_saved(
            event.client, target, reason="overwrite via .pushfile",
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    if ext == ".py":
        try:
            compile(raw.decode("utf-8"), str(target), "exec")
        except SyntaxError as e:
            await event.edit(Messages.error(
                f"Syntax error: {e.msg} @ {e.lineno}"))
            return
    target.write_bytes(raw)

    lines = [
        f"✅ Wrote `{target.relative_to(ROOT)}` · "
        f"{Formatters.format_size(len(raw))}",
    ]
    if backup_msg_id:
        lines.append(f"Previous version: Saved Messages (msg `{backup_msg_id}`)")
    await event.edit("\n".join(lines))


@command(r"readfile (.+)", "Send a project file here", permission="sudo")
async def readfile(event):
    target = _safe(event.pattern_match.group(1))
    if not target or not target.is_file():
        await event.edit(Messages.error("Not found or unsafe."))
        return
    buf = io.BytesIO(target.read_bytes())
    buf.name = target.name
    await event.client.send_file(
        event.chat_id, buf, force_document=True,
        caption=f"📄 `{target.relative_to(ROOT)}`",
    )
    try:
        await event.delete()
    except Exception:
        pass


@command(r"lsfile(?: (.+))?", "List project directory", permission="sudo")
async def lsfile(event):
    raw = (event.pattern_match.group(1) or "").strip()
    target = _safe(raw) if raw else ROOT
    if target is None or not target.is_dir():
        await event.edit(Messages.error("Not a directory."))
        return
    entries = sorted(target.iterdir(),
                     key=lambda p: (p.is_file(), p.name.lower()))
    lines = [f"📁 `{target.relative_to(ROOT)}`", SEP_FANCY]
    for p in entries[:60]:
        if p.name in PROTECTED or p.name in PROTECTED_DIRS:
            continue
        if p.is_dir():
            lines.append(f"📂 `{p.name}/`")
        else:
            lines.append(
                f"📄 `{p.name}` · {Formatters.format_size(p.stat().st_size)}")
    await event.edit("\n".join(lines))


@command(r"rmfile2 (.+)", "Delete project file (backup to Saved first)",
         permission="sudo")
async def rmfile2(event):
    target = _safe(event.pattern_match.group(1))
    if not target or not target.is_file():
        await event.edit(Messages.error("Not found or unsafe."))
        return
    msg_id = await _backup_saved(event.client, target, reason="delete via .rmfile2")
    if msg_id is None:
        await event.edit(Messages.error(
            "Backup to Saved Messages failed. File NOT deleted."))
        return
    try:
        target.unlink()
    except Exception as e:
        await event.edit(Messages.error(f"Delete failed: {e}"))
        return
    await event.edit(Messages.success(
        f"Deleted `{target.relative_to(ROOT)}`.\n"
        f"Backup: Saved Messages (msg `{msg_id}`)."))


# ═══════════════════════════════════════════════════════════════════
#  list / restore file backups
# ═══════════════════════════════════════════════════════════════════

@command("filebackups", "List file backups in Saved Messages", permission="sudo")
async def filebackups(event):
    await event.edit(Messages.loading("Searching Saved Messages…"))
    try:
        msgs = await event.client.get_messages(
            "me", search=FILE_BACKUP_TAG, limit=50,
        )
    except Exception as e:
        await event.edit(Messages.error(f"Search failed: {e}"))
        return
    if not msgs:
        await event.edit(Messages.info("No file backups found."))
        return
    lines = [f"🗂 **{len(msgs)} file backup(s)**", SEP_FANCY]
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
        "\n_Restore: reply to a backup file in Saved Messages with `.filrestore`_"
    )
    await event.edit("\n".join(lines))


@command("filrestore", "Restore a file from a Saved Messages backup",
         permission="sudo")
async def filrestore(event):
    """Reply to a file backup in Saved Messages. Filename determines target path."""
    if not event.is_reply:
        await event.edit(Messages.error(
            "Reply to a backup file in Saved Messages."))
        return
    replied = await event.get_reply_message()
    if not replied or not replied.document:
        await event.edit(Messages.error("Replied message has no file."))
        return

    # parse the original path from the caption
    target_rel = None
    caption = replied.message or ""
    for line in caption.splitlines():
        if line.startswith("**Path:**"):
            target_rel = line.split("`")[1] if "`" in line else None
            break

    if not target_rel:
        await event.edit(Messages.error(
            "Could not find the original path in the caption.\n"
            "Restore manually with `.pushfile <path>`."))
        return

    target = _safe(target_rel)
    if target is None:
        await event.edit(Messages.error(
            f"Path `{target_rel}` is now unsafe. Cannot restore."))
        return

    await event.edit(Messages.loading(f"Restoring `{target_rel}`…"))

    buf = io.BytesIO()
    try:
        await event.client.download_media(replied, file=buf)
        buf.seek(0)
        raw = buf.read()
    except Exception as e:
        await event.edit(Messages.error(f"Download failed: {e}"))
        return

    # back up whatever is currently there
    if target.exists():
        await _backup_saved(
            event.client, target,
            reason=f"overwrite via .filrestore from msg {replied.id}",
        )

    if target.suffix.lower() == ".py":
        try:
            compile(raw.decode("utf-8"), str(target), "exec")
        except SyntaxError as e:
            await event.edit(Messages.error(
                f"Syntax error in backup: {e.msg} @ {e.lineno}"))
            return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)

    await event.edit(Messages.success(
        f"Restored `{target.relative_to(ROOT)}`.\n"
        f"_If it was a plugin, use `.modreload <name>` or `.restart`._"))


@command("filehelp", "Files help")
async def filehelp(event):
    await event.edit(
        "📁 **FILES**\n"
        f"{SEP_FANCY}\n\n"
        "**Push / read / list / delete:**\n"
        "▸ `.pushfile <path>` — reply to a file\n"
        "▸ `.readfile <path>` — send file to this chat\n"
        "▸ `.lsfile [dir]` — list directory\n"
        "▸ `.rmfile2 <path>` — backup + delete\n\n"
        "**Backups (Saved Messages only, no disk):**\n"
        "▸ `.filebackups` — list backups in Saved\n"
        "▸ `.filrestore` — reply to a backup to restore\n\n"
        f"{SEP_FANCY}\n"
        "**Safety:**\n"
        "• Refuses `.env`, `*.session`, `venv/`, `.git/`, `data/`\n"
        "• Syntax-checks `.py` before writing\n"
        "• Every overwrite backed up to Saved first"
    )