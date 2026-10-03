"""Selftest — check every registered command compiles."""
import re

from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="selftest", category="developer",
    description="Check that every registered command's pattern compiles.",
    permission="sudo",
)


@command("selftest", "Run pattern self-test", permission="sudo")
async def selftest(event):
    reg = event.ctx.registry
    broken = []
    for name, meta in reg.commands.items():
        try:
            re.compile(meta["pattern"])
        except re.error as e:
            broken.append((name, str(e)))
    if not broken:
        stats = reg.get_stats()
        await event.edit(
            f"🔬 **Self-test**\n{SEP_FANCY}\n"
            f"✅ All **{stats['total_commands']}** commands OK.\n"
            f"modules: {stats['total_modules']} · handlers: {stats['total_handlers']}"
        )
        return
    lines = [f"🔬 **{len(broken)} broken**", SEP_FANCY]
    for n, e in broken[:30]:
        lines.append(f"❌ `{n}` — _{e[:50]}_")
    await event.edit("\n".join(lines))


@command("cmds", "List all registered commands", permission="sudo")
async def cmds(event):
    reg = event.ctx.registry
    by_mod = {}
    for name, meta in reg.commands.items():
        by_mod.setdefault(meta["module"], []).append(name)
    lines = [f"📋 **{len(reg.commands)} commands**", SEP_FANCY]
    for mod in sorted(by_mod):
        names = sorted(by_mod[mod])
        lines.append(f"\n**{mod}** · {len(names)}")
        for i in range(0, len(names), 4):
            lines.append("  ".join(f"`{n}`" for n in names[i:i+4]))
    text = "\n".join(lines)
    await event.edit(text[:3900])


@command("count", "Command counts", permission="sudo")
async def count(event):
    stats = event.ctx.registry.get_stats()
    await event.edit(
        f"📊 **Counts**\n{SEP_FANCY}\n"
        f"Commands: {stats['total_commands']}\n"
        f"Modules: {stats['total_modules']}\n"
        f"Handlers: {stats['total_handlers']}\n"
        f"Categories: {stats['categories']}"
    )
