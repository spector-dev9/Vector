""".export / .exportfull — project zip to Saved Messages."""
import io
import time
import zipfile
from pathlib import Path

from core.decorators import command
from core.module import ModuleMeta
from Config.settings import Config
from utils import Messages, SEP_FANCY, Formatters

META = ModuleMeta(
    name="export", category="sudo",
    description="Zip the project (code-only or full) and send to Saved Messages.",
    permission="sudo",
)

ROOT = Path(Config.BASE_DIR)

_EXCLUDE_CODE_DIRS = {".git", "__pycache__", "data", "logs",
                      "venv", ".venv", "env"}
_EXCLUDE_CODE_NAMES = {".env", "session"}
_EXCLUDE_CODE_SUFFIX = (".session", ".session-journal", ".pyc", ".pyo", ".db")

_EXCLUDE_FULL_DIRS = {".git", "__pycache__", "venv", ".venv", "env"}
_EXCLUDE_FULL_SUFFIX = (".pyc", ".pyo")

EXPORT_TAG = "#vector_export"
EXPORTFULL_TAG = "#vector_export_full"


def _zip(root: Path, exclude_dirs: set, exclude_names: set,
         exclude_suffix: tuple) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(root)
            if any(p in exclude_dirs for p in rel.parts):
                continue
            if f.name in exclude_names:
                continue
            if any(f.name.endswith(s) for s in exclude_suffix):
                continue
            zf.write(f, arcname=str(rel))
    buf.seek(0)
    return buf.read()


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


# ═══════════════════════════════════════════════════════════════════
#  .export — code-only
# ═══════════════════════════════════════════════════════════════════

@command("export", "Code-only project zip → Saved Messages",
         permission="sudo")
async def export(event):
    await event.edit(Messages.loading("Building code-only zip…"))
    try:
        data = _zip(ROOT, _EXCLUDE_CODE_DIRS,
                    _EXCLUDE_CODE_NAMES, _EXCLUDE_CODE_SUFFIX)
    except Exception as e:
        await event.edit(Messages.error(f"Zip failed: {e}"))
        return

    fname = f"vector_code_{_ts()}.zip"
    buf = io.BytesIO(data)
    buf.name = fname

    caption = (
        f"{EXPORT_TAG}\n"
        f"📦 **VECTOR — code-only export**\n"
        f"**File:** `{fname}`\n"
        f"**Size:** {Formatters.format_size(len(data))}\n"
        f"**When:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**Includes:** source code, plugins, configs\n"
        f"**Excludes:** `.env`, sessions, `data/`, `logs/`\n"
    )

    try:
        sent = await event.client.send_file(
            "me", buf, caption=caption, force_document=True,
        )
    except Exception as e:
        await event.edit(Messages.error(f"Send failed: {e}"))
        return

    await event.edit(Messages.success(
        f"Code-only export sent to Saved Messages.\n"
        f"File: `{fname}` · {Formatters.format_size(len(data))}\n"
        f"Msg id: `{sent.id}`"))


# ═══════════════════════════════════════════════════════════════════
#  .exportfull — everything including secrets
# ═══════════════════════════════════════════════════════════════════

@command("exportfull", "FULL zip (secrets + DB) → Saved Messages",
         permission="sudo")
async def exportfull(event):
    await event.edit(Messages.loading("Building full backup…"))
    try:
        data = _zip(ROOT, _EXCLUDE_FULL_DIRS, set(), _EXCLUDE_FULL_SUFFIX)
    except Exception as e:
        await event.edit(Messages.error(f"Zip failed: {e}"))
        return

    size_mb = len(data) / (1024 * 1024)
    if size_mb > 45:
        await event.edit(Messages.error(
            f"Too big: {size_mb:.1f} MB (limit ~45 MB)."))
        return

    fname = f"vector_full_{_ts()}.zip"
    buf = io.BytesIO(data)
    buf.name = fname

    caption = (
        f"{EXPORTFULL_TAG}\n"
        f"🔐 **VECTOR — FULL backup**\n"
        f"**File:** `{fname}`\n"
        f"**Size:** {Formatters.format_size(len(data))}\n"
        f"**When:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⚠️ **Contains secrets** — `.env`, sessions, DBs, logs\n"
        f"_Delete after you've stored it somewhere safe._"
    )

    try:
        sent = await event.client.send_file(
            "me", buf, caption=caption, force_document=True,
        )
    except Exception as e:
        await event.edit(Messages.error(f"Send failed: {e}"))
        return

    await event.edit(Messages.success(
        f"FULL backup sent to Saved Messages.\n"
        f"File: `{fname}` · {Formatters.format_size(len(data))}\n"
        f"Msg id: `{sent.id}`\n"
        f"_Contains secrets._"))


# ═══════════════════════════════════════════════════════════════════
#  .exports — list exports in Saved
# ═══════════════════════════════════════════════════════════════════

@command("exports", "List recent exports in Saved Messages",
         permission="sudo")
async def exports(event):
    await event.edit(Messages.loading("Searching Saved Messages…"))
    try:
        code_msgs = await event.client.get_messages(
            "me", search=EXPORT_TAG, limit=20,
        )
        full_msgs = await event.client.get_messages(
            "me", search=EXPORTFULL_TAG, limit=20,
        )
    except Exception as e:
        await event.edit(Messages.error(f"Search failed: {e}"))
        return

    all_msgs = []
    for m in code_msgs:
        all_msgs.append(("code", m))
    for m in full_msgs:
        all_msgs.append(("full", m))
    all_msgs.sort(key=lambda x: x[1].date, reverse=True)

    if not all_msgs:
        await event.edit(Messages.info("No exports found."))
        return

    lines = [f"📦 **{len(all_msgs)} export(s)**", SEP_FANCY]
    for kind, m in all_msgs[:25]:
        icon = "🔐" if kind == "full" else "📦"
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
        lines.append(f"{icon} `{fname}` · {when} · msg `{m.id}`")

    if len(all_msgs) > 25:
        lines.append(f"_…+{len(all_msgs)-25} more_")
    lines.append(f"\n{SEP_FANCY}")
    lines.append("📦 code-only · 🔐 full (secrets)")
    await event.edit("\n".join(lines))


@command("exporthelp", "Export help")
async def exporthelp(event):
    await event.edit(
        "📦 **EXPORT**\n"
        f"{SEP_FANCY}\n\n"
        "▸ `.export` — code-only zip → Saved Messages\n"
        "▸ `.exportfull` — FULL zip incl. secrets → Saved\n"
        "▸ `.exports` — list past exports in Saved\n\n"
        f"{SEP_FANCY}\n"
        "**Code-only excludes:**\n"
        "`.env`, sessions, `data/`, `logs/`, venv, .git\n\n"
        "**Full includes:**\n"
        "everything above, plus DBs, sessions, logs\n\n"
        "⚠️ `.exportfull` file contains your credentials. "
        "Move it off Telegram after download."
    )