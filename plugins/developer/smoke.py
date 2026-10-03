"""Smoke — fire non-destructive commands."""
import asyncio

from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="smoke", category="developer",
    description="Live-test non-destructive commands.",
    permission="sudo",
)

_SKIP = {
    "restart", "shutdown", "moddel", "modunload", "modreload",
    "modload", "modreloadall", "rmfile", "rmfile2", "presetdel",
    "notedel", "filterdel", "logdel", "export", "exportfull",
    "spam", "spamstop", "selftest", "smoke", "cmds", "count",
    "root", "unzip", "grabbatch", "download", "dlfile",
    "yta", "ytv", "rnup", "clone", "kang", "save", "note", "filter",
    "warn", "lock", "unlock", "addblacklist", "rmblacklist",
    "addblkchat", "rmblkchat", "setflood", "pmguard", "approve",
    "disapprove", "block", "unblock", "schedule", "autoschedule",
    "delschedule", "sessionkiller", "eval", "exec", "inspect", "pysh",
    "sh", "modhealth", "modenable", "modenableall", "moddisable",
}

_NO_ARG_OK = {
    "ping", "p", "alive", "help", "count", "modlist", "cmds",
    "top10", "joke", "quote", "fact", "uuid", "randomcolor",
    "notes", "presets", "tracked", "sessions", "filters",
    "warns", "locks", "listapproved", "listblacklist", "listblkchat",
    "listwelcome", "myschedule", "stkinfo", "getthumb",
    "status", "authsessions", "modhealth",
    "gameshelp", "vexhelp", "mathhelp", "webhelp", "texthelp",
    "loglist", "loghelp",
}


@command(r"smoke(?:\s+(\w+))?", "Live-test commands", permission="sudo")
async def smoke(event):
    reg = event.ctx.registry
    target = (event.pattern_match.group(1) or "").strip().lower()
    cmds = [
        (n, m) for n, m in reg.commands.items()
        if n not in _SKIP and (not target or m.get("module", "").lower() == target)
    ]
    total = len(cmds)
    await event.edit(f"🔥 Testing {total}…")
    await asyncio.sleep(0.5)
    failures = []
    tested = skipped = 0
    for name, _ in cmds:
        if name not in _NO_ARG_OK:
            skipped += 1
            continue
        tested += 1
        try:
            sent = await event.client.send_message("me", f".{name}")
            await asyncio.sleep(1.2)
            fetched = await event.client.get_messages("me", ids=sent.id)
            text = (fetched.raw_text or "") if fetched else ""
            if "❌" in text or "Error" in text or text.startswith(f".{name}"):
                failures.append((name, text[:80]))
            try:
                await event.client.delete_messages("me", [sent.id])
            except Exception:
                pass
        except Exception as e:
            failures.append((name, f"{type(e).__name__}: {e}"))
    lines = [
        "🔥 **Smoke done**", SEP_FANCY,
        f"✅ passed: {tested - len(failures)}",
        f"❌ failed: {len(failures)}",
        f"⏭️ skipped: {skipped}",
    ]
    if failures:
        lines.append("\n**Failures:**")
        for n, err in failures[:20]:
            lines.append(f"❌ `{n}` — _{err}_")
    await event.edit("\n".join(lines))
