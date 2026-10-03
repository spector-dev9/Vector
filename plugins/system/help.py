"""Help — metadata-driven."""
from Config.settings import Config
from core.module import ModuleMeta
from core.decorators import command
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="help", category="system",
    description="Browse commands, categories and modules.",
    permission="user",
)

_EMOJI = {
    "root": "🔑", "sudo": "👑", "account": "👤", "telegram": "✈️",
    "moderation": "🛡", "automation": "🤖", "media": "🎬",
    "tools": "🛠", "developer": "🧰", "fun": "🎮", "system": "⚙️",
}

_LOGO = (
    "╔══════════════════════════════╗\n"
    "║      ⚡  V E C T O R  ⚡     ║\n"
    "║   multi-account userbot      ║\n"
    "╚══════════════════════════════╝"
)


@command("help(?:\\s+(.+))?", "Show help")
async def help_handler(event):
    ctx = event.ctx
    reg = ctx.registry
    q = (event.pattern_match.group(1) or "").strip().lower()
    if not q:
        await _menu(event, reg)
    elif q in ("all", "everything"):
        await _all(event, reg)
    else:
        ci = reg.get_command_info(q)
        if ci:
            await _cmd(event, ci)
            return
        if q in [c.lower() for c in reg.get_all_categories()]:
            await _cat(event, reg, q)
            return
        results = reg.search_commands(q)
        if results:
            await _search(event, results, q)
            return
        await event.edit(Messages.error(f"Not found: `{q}`"))


async def _menu(event, reg):
    stats = reg.get_stats()
    by_cat = reg.get_commands_by_category()
    text = (
        f"{_LOGO}\n\n{SEP_FANCY}\n"
        f"**Commands**  `{stats['total_commands']}`\n"
        f"**Modules**   `{stats['total_modules']}`\n"
        f"**Handlers**  `{stats['total_handlers']}`\n"
        f"**Prefix**    `{Config.CMD_PREFIX}`\n"
        f"**Version**   `{Config.VERSION}`\n"
        f"{SEP_FANCY}\n\n**Access**\n"
        "▸ `.help all`\n▸ `.help <category>`\n▸ `.help <command>`\n"
    )
    for cat in sorted(by_cat):
        cmds = by_cat[cat]
        emoji = _EMOJI.get(cat, "📦")
        text += f"\n{emoji} **{cat.upper()}** · {len(cmds)}\n"
        for c in cmds[:4]:
            lock = "🔒 " if c["permission"] in ("sudo", "root") else "   "
            text += f"{lock}`{c['name']}`\n"
        if len(cmds) > 4:
            text += f"    _…+{len(cmds)-4} more_\n"
    await event.edit(text[:3900])


async def _all(event, reg):
    by_cat = reg.get_commands_by_category()
    text = f"{_LOGO}\n\n📚 **FULL REFERENCE**\n{SEP_FANCY}\n"
    for cat in sorted(by_cat):
        text += f"\n{_EMOJI.get(cat, '📦')} **{cat.upper()}**\n"
        for c in by_cat[cat]:
            lock = "🔒 " if c["permission"] in ("sudo", "root") else ""
            desc = f" — _{c['description']}_" if c["description"] else ""
            text += f"{lock}`{Config.CMD_PREFIX}{c['name']}`{desc}\n"
    await event.edit(text[:3900])


async def _cat(event, reg, cat):
    by_cat = reg.get_commands_by_category(cat)
    if cat not in by_cat:
        await event.edit(Messages.error("No such category."))
        return
    text = f"{_EMOJI.get(cat, '📦')} **{cat.upper()}** · {len(by_cat[cat])}\n{SEP_FANCY}\n"
    for c in by_cat[cat]:
        lock = "🔒 " if c["permission"] in ("sudo", "root") else "▸ "
        desc = f" _({c['description']})_" if c["description"] else ""
        text += f"{lock}`{Config.CMD_PREFIX}{c['name']}`{desc}\n"
    await event.edit(text)


async def _cmd(event, ci):
    lock = "🔒 " if ci["permission"] in ("sudo", "root") else ""
    text = (
        f"📖 **COMMAND**\n{SEP_FANCY}\n\n"
        f"{lock}**`{Config.CMD_PREFIX}{ci['name']}`**\n"
        f"**Category** {ci['category']}\n"
        f"**Permission** `{ci['permission']}`\n"
    )
    if ci["description"]:
        text += f"\n_{ci['description']}_\n"
    if ci.get("docstring"):
        text += f"\n```\n{ci['docstring'][:800]}\n```"
    await event.edit(text)


async def _search(event, results, q):
    text = f"🔍 **{len(results)} result(s)** for `{q}`\n{SEP_FANCY}\n"
    by_cat = {}
    for c in results:
        by_cat.setdefault(c["category"], []).append(c)
    for cat in sorted(by_cat):
        text += f"\n{_EMOJI.get(cat, '📦')} **{cat.upper()}**\n"
        for c in by_cat[cat][:5]:
            lock = "🔒 " if c["permission"] in ("sudo", "root") else "▸ "
            text += f"{lock}`{c['name']}` — _{c['description']}_\n"
    await event.edit(text[:3900])
