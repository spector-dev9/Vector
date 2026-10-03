"""Filters."""
from telethon import events
from sqlalchemy import select

from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import Filter
from utils import Messages

META = ModuleMeta(
    name="filters", category="automation",
    description="Keyword-triggered auto-replies.",
    permission="user",
)


@command(r"filter (\w+) (.+)", "Add filter")
async def add(event):
    ctx = event.ctx
    keyword = event.pattern_match.group(1).lower()
    response = event.pattern_match.group(2)
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Filter).where(
            Filter.user_id == me.id, Filter.keyword == keyword))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(Filter(user_id=me.id, keyword=keyword, response=response))
            action = "added"
        else:
            row.response = response
            action = "updated"
    await event.edit(Messages.success(f"Filter `{keyword}` {action}."))


@command(r"filterdel (\w+)", "Remove filter")
async def remove(event):
    ctx = event.ctx
    keyword = event.pattern_match.group(1).lower()
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Filter).where(
            Filter.user_id == me.id, Filter.keyword == keyword))
        row = r.scalar_one_or_none()
        if row is None:
            await event.edit(Messages.error(f"`{keyword}` not found."))
            return
        await s.delete(row)
    await event.edit(Messages.success(f"Filter `{keyword}` removed."))


@command("filters", "List filters")
async def list_filters(event):
    ctx = event.ctx
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Filter).where(Filter.user_id == me.id))
        rows = r.scalars().all()
    if not rows:
        await event.edit(Messages.info("No filters."))
        return
    lines = ["🎯 **Filters**\n"]
    for r in rows:
        preview = r.response[:40] + "…" if len(r.response) > 40 else r.response
        lines.append(f"• `{r.keyword}` → {preview}")
    await event.edit("\n".join(lines))


@command("filterclear", "Delete all filters")
async def clear(event):
    ctx = event.ctx
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Filter).where(Filter.user_id == me.id))
        rows = r.scalars().all()
        for row in rows:
            await s.delete(row)
    await event.edit(Messages.success(f"Cleared {len(rows)} filter(s)."))


@listener(events.NewMessage(incoming=True))
async def watcher(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None or not event.raw_text:
        return
    me = await event.client.get_me()
    if event.sender_id == me.id:
        return
    try:
        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            return
    except Exception:
        pass
    text = event.raw_text.lower()
    async with ctx.database.session() as s:
        r = await s.execute(select(Filter).where(Filter.user_id == me.id))
        rows = r.scalars().all()
    hits = [x for x in rows if x.keyword in text]
    if not hits:
        return
    hits.sort(key=lambda x: len(x.keyword), reverse=True)
    try:
        await event.reply(hits[0].response)
    except Exception:
        pass
