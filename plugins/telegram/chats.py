""".open / .dm."""
from telethon import Button
from core.decorators import command
from core.module import ModuleMeta
from helpers.telegram.chats import chat_kind, resolve_chat
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="chats", category="telegram",
    description="Open a chat by ID, or DM a user by ID.",
    permission="sudo",
)


def _name(e):
    return (getattr(e, "title", None) or
            f"{getattr(e, 'first_name', '') or ''} "
            f"{getattr(e, 'last_name', '') or ''}".strip() or "—")


def _open_url(e, resolved):
    username = getattr(e, "username", None)
    kind = chat_kind(e)
    eid = getattr(e, "id", resolved)
    if username:
        return f"https://t.me/{username}"
    if kind in ("user", "bot"):
        return f"https://t.me/@id{eid}"
    if kind in ("channel", "supergroup"):
        cid = str(resolved)
        cid = cid[4:] if cid.startswith("-100") else cid.lstrip("-")
        return f"https://t.me/c/{cid}"
    return None


@command(r"open(?:\s+(\S+))?", "Open a chat by ID", permission="sudo")
async def open_cmd(event):
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        await event.edit(Messages.error("Usage: `.open <id>`"))
        return
    await event.edit(Messages.loading(f"Opening `{raw}`…"))
    entity = await resolve_chat(event.client, raw)
    if entity is None:
        await event.edit(Messages.error(f"Couldn't resolve `{raw}`."))
        return
    kind = chat_kind(entity)
    name = _name(entity)
    try:
        await event.client.send_message(entity, ".")
        opened = "✅"
    except Exception:
        opened = "❌"
    card = (
        f"🎯 **OPENED**\n{SEP_FANCY}\n"
        f"Type: `{kind}`\nName: **{name}**\n"
        f"ID: `{getattr(entity, 'id', raw)}`\nOpened: {opened}"
    )
    url = _open_url(entity, raw)
    if url:
        await event.edit(card, buttons=[[Button.url("💬 Open", url)]])
    else:
        await event.edit(card)


@command(r"dm(?:\s+(\S+))(?:\s+(.+))?", "Send a message by ID", permission="sudo")
async def dm(event):
    raw = (event.pattern_match.group(1) or "").strip()
    text = event.pattern_match.group(2) or ""
    if not raw or not text:
        await event.edit(Messages.error("Usage: `.dm <id> <text>`"))
        return
    entity = await resolve_chat(event.client, raw)
    if entity is None:
        await event.edit(Messages.error("Couldn't resolve."))
        return
    try:
        await event.client.send_message(entity, text)
    except Exception as e:
        await event.edit(Messages.error(str(e)))
        return
    await event.edit(Messages.success(f"Sent to **{_name(entity)}**."))
