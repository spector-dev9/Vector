""".info / .whois / .getid / .chatid."""
from telethon import functions
from core.decorators import command
from core.module import ModuleMeta
from helpers.telegram.messages import resolve_target
from utils import Messages

META = ModuleMeta(
    name="identity", category="root",
    description="User and chat identity lookups (never leaks phone).",
    permission="user",
)


@command(r"info(?:\s+(.+))?", "User info")
async def info(event):
    u = await resolve_target(event.client, event, event.pattern_match.group(1))
    if u is None:
        u = await event.get_sender()
    name = f"{getattr(u,'first_name','') or ''} {getattr(u,'last_name','') or ''}".strip() or "—"
    await event.edit(
        f"👤 **{name}**\n"
        f"**ID:** `{u.id}`\n"
        f"**Username:** @{getattr(u,'username',None) or '—'}\n"
        f"**Bot:** {'yes' if getattr(u,'bot',False) else 'no'}\n"
        f"**Premium:** {'yes' if getattr(u,'premium',False) else 'no'}"
    )


@command(r"whois(?:\s+(.+))?", "Detailed lookup")
async def whois(event):
    u = await resolve_target(event.client, event, event.pattern_match.group(1))
    if u is None:
        await event.edit(Messages.error("Couldn't resolve."))
        return
    try:
        full = await event.client(functions.users.GetFullUserRequest(id=u.id))
        fu = full.full_user
        bio = fu.about or "—"
        commons = getattr(fu, "common_chats_count", 0) or 0
    except Exception:
        bio, commons = "—", 0
    await event.edit(
        f"🔎 **Whois**\n**ID:** `{u.id}`\n"
        f"**Username:** @{getattr(u,'username',None) or '—'}\n"
        f"**Bio:** {bio}\n**Common chats:** {commons}"
    )


@command(r"getid(?:\s+(.+))?", "Show IDs")
async def getid(event):
    lines = ["🆔 **IDs**\n", f"**Chat:** `{event.chat_id}`"]
    if event.is_reply:
        replied = await event.get_reply_message()
        sender = await replied.get_sender()
        if sender:
            lines.append(f"**Replied user:** `{sender.id}`")
        lines.append(f"**Replied msg:** `{replied.id}`")
    lines.append(f"**This msg:** `{event.message.id}`")
    await event.edit("\n".join(lines))


@command("chatid", "Show current chat id")
async def chatid(event):
    await event.edit(f"🆔 `{event.chat_id}`")
