"""Unzip — safe extraction."""
import asyncio
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from telethon.errors import FloodWaitError

from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, Formatters

META = ModuleMeta(
    name="unzip", category="media",
    description="Extract archives and forward contents with pause/resume.",
    permission="sudo",
)

SEND_DELAY = 1.2
MAX_FILES = 300
MAX_SIZE_PER_FILE = 1.9 * 1024 * 1024 * 1024
MAX_TOTAL_EXTRACT = 3 * 1024 * 1024 * 1024
ARCHIVE_EXTS = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")

_state = {}


def _ctl(account_id, cid):
    return _state.setdefault(
        (account_id, cid),
        {"stop": False, "pause": False, "active": False},
    )


def _is_archive(name):
    return any(name.lower().endswith(e) for e in ARCHIVE_EXTS)


def _safe_target(dest: Path, member: str) -> bool:
    """Reject path traversal."""
    try:
        target = (dest / member).resolve()
        target.relative_to(dest.resolve())
        return True
    except ValueError:
        return False


def _extract(path, dest) -> list:
    """Safe extraction with size and traversal checks."""
    name = path.name.lower()
    dest.mkdir(parents=True, exist_ok=True)
    if name.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            total = 0
            infos = zf.infolist()
            regular_count = 0
            for info in infos:
                if not _safe_target(dest, info.filename):
                    raise ValueError(f"unsafe member: {info.filename}")
                if not info.is_dir():
                    regular_count += 1
                    if regular_count > MAX_FILES:
                        raise ValueError(f"archive has more than {MAX_FILES} files")
                total += info.file_size
                if total > MAX_TOTAL_EXTRACT:
                    raise ValueError(f"archive too large: {total} bytes")
            zf.extractall(dest)
            return [info.filename for info in infos]
    with tarfile.open(path) as tf:
        total = 0
        members = tf.getmembers()
        regular_count = 0
        for m in members:
            if not _safe_target(dest, m.name):
                raise ValueError(f"unsafe member: {m.name}")
            if m.issym() or m.islnk():
                raise ValueError(f"links not allowed: {m.name}")
            if m.isfile():
                regular_count += 1
                if regular_count > MAX_FILES:
                    raise ValueError(f"archive has more than {MAX_FILES} files")
            total += m.size
            if total > MAX_TOTAL_EXTRACT:
                raise ValueError(f"archive too large: {total} bytes")
        tf.extractall(dest)
        return [m.name for m in members]


async def _send_one(client, chat_id, p: Path, rel: str, attempt=0) -> bool:
    if not p.is_file() or p.stat().st_size > MAX_SIZE_PER_FILE:
        return False
    try:
        await client.send_file(
            chat_id, str(p),
            caption=f"`{rel}` · {Formatters.format_size(p.stat().st_size)}",
            force_document=True,
        )
        return True
    except FloodWaitError as e:
        await asyncio.sleep(int(e.seconds) + 2)
        if attempt < 2:
            return await _send_one(client, chat_id, p, rel, attempt + 1)
        return False
    except Exception:
        return False


async def _paused(account_id, cid):
    c = _ctl(account_id, cid)
    while c["pause"] and not c["stop"]:
        await asyncio.sleep(0.5)
    return not c["stop"]


@command("unzip", "Extract and forward every file", permission="sudo")
async def unzip(event):
    if not event.is_reply:
        await event.edit(Messages.error("Reply to an archive."))
        return
    replied = await event.get_reply_message()
    if not replied or not replied.document:
        await event.edit(Messages.error("No file."))
        return
    fname = None
    for a in replied.document.attributes or []:
        if getattr(a, "file_name", None):
            fname = a.file_name
            break
    if not fname or not _is_archive(fname):
        await event.edit(Messages.error("Unsupported."))
        return
    account_id = event.ctx.account_id
    cid = event.chat_id
    key = (account_id, cid)
    _state[key] = {"stop": False, "pause": False, "active": True}
    c = _ctl(account_id, cid)
    await event.edit(Messages.loading(f"Downloading `{fname}`…"))
    tmp = Path(tempfile.mkdtemp(prefix="vector_unzip_"))
    try:
        ap = tmp / fname
        await event.client.download_media(replied, file=str(ap))
        await event.edit(Messages.loading("Extracting…"))
        entries = _extract(ap, tmp / "out")
        files = [e for e in entries if (tmp / "out" / e).is_file()]
        if not files:
            await event.edit(Messages.info("Archive is empty."))
            return
        if len(files) > MAX_FILES:
            await event.edit(Messages.error(f"{len(files)} files (cap {MAX_FILES})."))
            return
        status = await event.edit(f"📦 Uploading {len(files)} files…")
        sent = failed = 0
        for i, rel in enumerate(files, 1):
            if not await _paused(account_id, cid):
                break
            ok = await _send_one(event.client, cid, tmp / "out" / rel, rel)
            sent += ok
            failed += (not ok)
            if i % 3 == 0 or i == len(files):
                try:
                    await status.edit(f"📦 {i}/{len(files)} · ✅{sent} ❌{failed}")
                except Exception:
                    pass
            await asyncio.sleep(SEND_DELAY)
        await status.edit(
            Messages.success(f"Sent **{sent}** · failed **{failed}**")
            if not c["stop"]
            else Messages.warning(f"Stopped at {sent}/{len(files)}"))
    except Exception as e:
        await event.edit(Messages.error(str(e)))
    finally:
        c["active"] = c["stop"] = c["pause"] = False
        shutil.rmtree(tmp, ignore_errors=True)


@command("unzippause", "Pause .unzip", permission="sudo")
async def unzippause(event):
    c = _ctl(event.ctx.account_id, event.chat_id)
    if not c["active"]:
        await event.edit(Messages.info("No unzip running."))
        return
    c["pause"] = True
    await event.edit(Messages.success("⏸ paused."))


@command("unzipresume", "Resume .unzip", permission="sudo")
async def unzipresume(event):
    c = _ctl(event.ctx.account_id, event.chat_id)
    if not c["active"]:
        await event.edit(Messages.info("No unzip."))
        return
    c["pause"] = False
    await event.edit(Messages.success("▶️ resumed."))


@command("unzipstop", "Stop .unzip", permission="sudo")
async def unzipstop(event):
    c = _ctl(event.ctx.account_id, event.chat_id)
    if not c["active"]:
        await event.edit(Messages.info("No unzip."))
        return
    c["stop"] = True
    c["pause"] = False
    await event.edit(Messages.success("⏹ stopping."))
