""".loglist / .logview / .logdel."""
from pathlib import Path
from datetime import datetime

from core.decorators import command
from core.module import ModuleMeta
from Config.settings import Config
from utils import Messages, SEP_FANCY, Formatters

META = ModuleMeta(
    name="logs", category="system",
    description="List, view, prune log files.",
    permission="sudo",
)


def _files():
    d = Path(Config.LOGS_DIR)
    if not d.exists():
        return []
    return sorted(
        (f for f in d.rglob("*.log") if f.is_file()),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )


@command("loglist", "List log files", permission="sudo")
async def loglist(event):
    files = _files()
    if not files:
        await event.edit(Messages.info("No log files."))
        return
    total = sum(f.stat().st_size for f in files)
    lines = [f"📄 **Logs** · {Formatters.format_size(total)} total", SEP_FANCY]
    for f in files[:20]:
        lines.append(f"▸ `{f.name}` · {Formatters.format_size(f.stat().st_size)}")
    await event.edit("\n".join(lines))


@command(r"logview(?:\s+(\d+))?", "Send newest log", permission="sudo")
async def logview(event):
    n = int(event.pattern_match.group(1) or 1)
    files = _files()
    if not files or n < 1 or n > len(files):
        await event.edit(Messages.error("Invalid."))
        return
    f = files[n - 1]
    await event.client.send_file("me", str(f), force_document=True,
                                 caption=f"`{f.name}`")
    await event.edit(Messages.success(f"Sent `{f.name}`."))


@command(r"logdel(?:\s+(all|old))?", "Delete log files", permission="sudo")
async def logdel(event):
    files = _files()
    today = datetime.now().strftime("%Y%m%d")
    active = f"vector_{today}.log"
    to_delete = [f for f in files if f.name != active]
    if not to_delete:
        await event.edit(Messages.info("Nothing to delete."))
        return
    freed = 0
    for f in to_delete:
        try:
            freed += f.stat().st_size
            f.unlink()
        except Exception:
            pass
    await event.edit(Messages.success(
        f"deleted {len(to_delete)} file(s) · {Formatters.format_size(freed)}"
    ))


@command("loghelp", "Log help")
async def loghelp(event):
    await event.edit(
        "📄 **LOGS**\n"
        "`.loglist` · `.logview [n]` · `.logdel [all|old]`"
    )
