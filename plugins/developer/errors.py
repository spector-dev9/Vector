""".errors / .errorsclear — recent per-account error history."""
from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="errors", category="developer",
    description="Inspect recent errors captured at runtime.",
    permission="sudo",
)


@command(r"errors(?:\s+(\d+))?", "Show recent errors", permission="sudo")
async def errors_cmd(event):
    handler = getattr(event.ctx, "errors", None)
    if handler is None or len(handler) == 0:
        await event.edit(Messages.info("No errors recorded."))
        return
    n = int(event.pattern_match.group(1) or 5)
    recent = handler.get_recent_errors(n)
    lines = [f"⚠️ **Recent errors** ({len(recent)}/{len(handler)})", SEP_FANCY]
    for e in recent:
        lines.append(
            f"\n**{e['timestamp']}** · `{e['type']}` · _{e['context']}_\n"
            f"`{e['error'][:200]}`"
        )
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n_…truncated_"
    await event.edit(text)


@command("errorsclear", "Clear the per-account error history", permission="sudo")
async def errors_clear(event):
    handler = getattr(event.ctx, "errors", None)
    if handler is None:
        await event.edit(Messages.error("No error handler bound."))
        return
    n = len(handler)
    handler.clear()
    await event.edit(Messages.success(f"Cleared {n} error(s)."))
