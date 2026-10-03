""".modhealth / .modenable / .moddisable — per-handler module health control."""
from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="health", category="sudo",
    description="Re-enable, disable, or inspect auto-disabled handlers.",
    permission="sudo",
)


@command("modhealth", "Show auto-disabled handlers for this account", permission="sudo")
async def modhealth(event):
    ctx = event.ctx
    mh = getattr(ctx, "module_health", None)
    if mh is None:
        await event.edit(Messages.info("No module health tracker bound."))
        return
    disabled = mh.disabled_list()
    if not disabled:
        await event.edit(Messages.info("No handlers currently disabled."))
        return
    lines = [f"⚠️ **Auto-disabled handlers** ({len(disabled)})", SEP_FANCY]
    for name in disabled:
        lines.append(f"• `{name}`")
    lines.append("\n_Re-enable with `.modenable <handler>`_")
    await event.edit("\n".join(lines))


@command(r"modenable (?P<name>\w+)", "Re-enable an auto-disabled handler", permission="sudo")
async def modenable(event):
    ctx = event.ctx
    mh = getattr(ctx, "module_health", None)
    if mh is None:
        await event.edit(Messages.error("No module health tracker bound."))
        return
    name = event.pattern_match.group("name")
    if mh.re_enable(name):
        await event.edit(Messages.success(f"Re-enabled `{name}`."))
    else:
        await event.edit(Messages.info(f"`{name}` was not disabled."))


@command("modenableall", "Re-enable every auto-disabled handler", permission="sudo")
async def modenableall(event):
    ctx = event.ctx
    mh = getattr(ctx, "module_health", None)
    if mh is None:
        await event.edit(Messages.error("No module health tracker bound."))
        return
    n = mh.re_enable_all()
    await event.edit(Messages.success(f"Re-enabled {n} handler(s)."))


@command(r"moddisable (?P<name>\w+)", "Manually disable a handler for this session", permission="sudo")
async def moddisable(event):
    ctx = event.ctx
    mh = getattr(ctx, "module_health", None)
    if mh is None:
        await event.edit(Messages.error("No module health tracker bound."))
        return
    name = event.pattern_match.group("name")
    if mh.disable(name):
        await event.edit(Messages.success(f"Disabled `{name}` for this session."))
    else:
        await event.edit(Messages.info(f"`{name}` was already disabled."))
