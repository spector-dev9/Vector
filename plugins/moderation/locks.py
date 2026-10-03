"""Locks."""
from telethon import events
from telethon.tl.types import (
    MessageEntityBotCommand, MessageEntityEmail,
    MessageEntityTextUrl, MessageEntityUrl,
)
from sqlalchemy import select

from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import Lock
from helpers.telegram.admins import is_admin
from utils import Messages

META = ModuleMeta(
    name="locks", category="moderation",
    description="Lock/unlock bots, commands, emails, forwards, URLs.",
    permission="sudo",
)

_LOCK_TYPES = ("bots", "commands", "email", "forward", "url")


async def _set(ctx, chat_id, field, value):
    async with ctx.database.session() as s:
        r = await s.execute(select(Lock).where(Lock.chat_id == chat_id))
        row = r.scalar_one_or_none()
        if row is None:
            row = Lock(chat_id=chat_id)
            s.add(row)
        setattr(row, field, value)


@command(r"lock(?:s)?(?:\s+(bots|commands|email|forward|url|all))?",
         "Lock a category", permission="sudo")
async def lock_cmd(event):
    ctx = event.ctx
    which = (event.pattern_match.group(1) or "").lower()
    if which not in _LOCK_TYPES and which != "all":
        await event.edit(Messages.error("Options: bots/commands/email/forward/url/all"))
        return
    targets = _LOCK_TYPES if which == "all" else (which,)
    for f in targets:
        await _set(ctx, event.chat_id, f, 1)
    await event.edit(Messages.success(f"Locked: `{which}`"))


@command(r"unlock(?:s)?(?:\s+(bots|commands|email|forward|url|all))?",
         "Unlock a category", permission="sudo")
async def unlock_cmd(event):
    ctx = event.ctx
    which = (event.pattern_match.group(1) or "").lower()
    if which not in _LOCK_TYPES and which != "all":
        await event.edit(Messages.error("Options: bots/commands/email/forward/url/all"))
        return
    targets = _LOCK_TYPES if which == "all" else (which,)
    for f in targets:
        await _set(ctx, event.chat_id, f, 0)
    await event.edit(Messages.success(f"Unlocked: `{which}`"))


@command("locks", "List active locks", permission="sudo")
async def list_locks(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(select(Lock).where(Lock.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
    if row is None:
        await event.edit(Messages.info("No locks here."))
        return
    lines = ["🔒 **Active locks**", ""]
    for f in _LOCK_TYPES:
        state = "🔒" if getattr(row, f) else "🔓"
        lines.append(f"{state}  `{f}`")
    await event.edit("\n".join(lines))


@listener(events.NewMessage(incoming=True))
async def _watcher(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None or event.is_private:
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(Lock).where(Lock.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
    if row is None:
        return
    me = await event.client.get_me()
    if not await is_admin(event.client, event.chat_id, me.id):
        return
    ent = event.message.entities or []

    def has(kind):
        return any(isinstance(e, kind) for e in ent)

    try:
        if row.bots:
            sender = await event.get_sender()
            if getattr(sender, "bot", False):
                await event.delete()
                return
        if row.commands and has(MessageEntityBotCommand):
            await event.delete()
            return
        if row.email and has(MessageEntityEmail):
            await event.delete()
            return
        if row.url and (has(MessageEntityUrl) or has(MessageEntityTextUrl)):
            await event.delete()
            return
        if row.forward and event.fwd_from:
            await event.delete()
            return
    except Exception:
        pass
