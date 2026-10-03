"""AFK — account-scoped."""
import asyncio
import time

from telethon import events
from sqlalchemy import select

from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import Afk
from utils import Messages, Formatters

META = ModuleMeta(
    name="afk", category="automation",
    description="AFK status with automatic replies.",
    permission="user",
)

_reply_ids = {}
_MAX = 500


def _reply_set(account_id):
    return _reply_ids.setdefault(account_id, set())


def _mark(account_id, chat_id, msg_id):
    bucket = _reply_set(account_id)
    bucket.add((chat_id, msg_id))
    while len(bucket) > _MAX:
        bucket.pop()


def _was_reply(account_id, chat_id, msg_id):
    bucket = _reply_set(account_id)
    key = (chat_id, msg_id)
    if key in bucket:
        bucket.discard(key)
        return True
    return False


@command(r"afk(?:\s+(.*))?", "Set AFK")
async def afk_set(event):
    ctx = event.ctx
    reason = (event.pattern_match.group(1) or "").strip() or "AFK"
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Afk).where(Afk.user_id == me.id))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(Afk(user_id=me.id, reason=reason, since=int(time.time())))
        else:
            row.reason = reason
            row.since = int(time.time())
    await event.edit(Messages.success(f"💤 AFK — {reason}"))


@command("unafk", "Clear AFK")
async def unafk(event):
    ctx = event.ctx
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Afk).where(Afk.user_id == me.id))
        row = r.scalar_one_or_none()
        if row is None:
            await event.edit(Messages.warning("Not AFK."))
            return
        elapsed = time.time() - row.since
        await s.delete(row)
    await event.edit(Messages.success(
        f"Welcome back — away {Formatters.format_duration(elapsed)}"
    ))


@listener(events.NewMessage(incoming=True))
async def afk_watcher(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None or event.sender_id is None:
        return
    me = await event.client.get_me()
    if event.sender_id == me.id:
        return
    if not event.is_private:
        replied_is_me = False
        if event.is_reply:
            try:
                r = await event.get_reply_message()
                replied_is_me = r is not None and r.sender_id == me.id
            except Exception:
                pass
        if not (event.mentioned or replied_is_me):
            return
    async with ctx.database.session() as s:
        r = await s.execute(select(Afk).where(Afk.user_id == me.id))
        row = r.scalar_one_or_none()
    if row is None:
        return
    text = (f"💤 **AFK** — {row.reason}\n"
            f"_Away {Formatters.format_duration(time.time() - row.since)}_")
    try:
        sent = await event.reply(text)
        if sent:
            _mark(ctx.account_id, sent.chat_id, sent.id)
    except Exception:
        pass


@listener(events.NewMessage(outgoing=True))
async def afk_clear(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None:
        return
    if _was_reply(ctx.account_id, event.chat_id, event.message.id):
        return
    me = await event.client.get_me()
    if event.chat_id == me.id:
        return
    text = event.raw_text or ""
    if text.startswith(ctx.config.CMD_PREFIX):
        rest = text[len(ctx.config.CMD_PREFIX):].strip().split()
        if rest and rest[0].lower() in ("afk", "unafk"):
            return
    async with ctx.database.session() as s:
        r = await s.execute(select(Afk).where(Afk.user_id == me.id))
        row = r.scalar_one_or_none()
        if row is None:
            return
        elapsed = time.time() - row.since
        await s.delete(row)
    try:
        note = await event.respond(
            f"✅ AFK cleared — away {Formatters.format_duration(elapsed)}"
        )
        _mark(ctx.account_id, note.chat_id, note.id)
        await asyncio.sleep(4)
        await note.delete()
    except Exception:
        pass
