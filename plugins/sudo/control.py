""".restart / .shutdown / .status / .root."""
import os
import sys
from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY, Formatters

META = ModuleMeta(
    name="control", category="sudo",
    description="Restart, shutdown, status, root toggle.",
    permission="sudo",
)


@command("restart", "Restart the process", permission="sudo")
async def restart(event):
    await event.edit(Messages.info("🔄 restarting…"))
    os.execl(sys.executable, sys.executable, *sys.argv)


@command("shutdown", "Shutdown the process", permission="sudo")
async def shutdown(event):
    await event.edit(Messages.info("🛑 shutting down…"))
    await event.client.disconnect()
    sys.exit(0)


@command("status", "Show status", permission="sudo")
async def status(event):
    ctx = event.ctx
    st = ctx.state.get_stats()
    reg = ctx.registry.get_stats()
    await event.edit(
        f"⚡ **VECTOR STATUS — {ctx.account_id}**\n{SEP_FANCY}\n"
        f"**Uptime**   {Formatters.format_uptime(ctx.state.started_at)}\n"
        f"**Commands** {st['commands']}\n"
        f"**Errors**   {st['errors']}\n"
        f"{SEP_FANCY}\n"
        f"📦 Modules  {reg['total_modules']}\n"
        f"🎁 Handlers {reg['total_handlers']}\n"
        f"📋 Commands {reg['total_commands']}"
    )


@command(r"root(?:\s+(unlock|lock))?", "Unlock/lock root-gated commands", permission="sudo")
async def root_toggle(event):
    ctx = event.ctx
    arg = (event.pattern_match.group(1) or "").lower()
    if arg == "unlock":
        ctx.meta["root_unlocked"] = True
        await event.edit(Messages.success("🔓 root unlocked."))
    elif arg == "lock":
        ctx.meta["root_unlocked"] = False
        await event.edit(Messages.success("🔒 root locked."))
    else:
        state = "unlocked" if ctx.meta.get("root_unlocked") else "locked"
        await event.edit(Messages.info(f"root is **{state}**"))
