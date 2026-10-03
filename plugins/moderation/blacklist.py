"""Blacklist."""
from telethon import events
from sqlalchemy import select

from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import BlacklistWord, BlacklistChat
from helpers.telegram.admins import is_admin
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="blacklist", category="moderation",
    description="Banned words in chats + global chat blacklist.",
    permission="sudo",
)


@command(r"addblacklist (?:(.+))", "Add blacklisted words", permission="sudo")
async def add_bl(event):
    ctx = event.ctx
    raw = event.pattern_match.group(1)
    words = [w.strip().lower() for w in raw.splitlines() if w.strip()]
    added = 0
    async with ctx.database.session() as s:
        for w in words:
            r = await s.execute(select(BlacklistWord).where(
                BlacklistWord.chat_id == event.chat_id,
                BlacklistWord.word == w))
            if r.scalar_one_or_none() is None:
                s.add(BlacklistWord(chat_id=event.chat_id, word=w))
                added += 1
    await event.edit(Messages.success(f"Added **{added}** word(s)."))


@command(r"rmblacklist (?:(.+))", "Remove blacklisted words", permission="sudo")
async def rm_bl(event):
    ctx = event.ctx
    words = [w.strip().lower()
             for w in (event.pattern_match.group(1) or "").splitlines() if w.strip()]
    removed = 0
    async with ctx.database.session() as s:
        for w in words:
            r = await s.execute(select(BlacklistWord).where(
                BlacklistWord.chat_id == event.chat_id,
                BlacklistWord.word == w))
            row = r.scalar_one_or_none()
            if row:
                await s.delete(row)
                removed += 1
    await event.edit(Messages.success(f"Removed **{removed}**."))


@command("listblacklist", "List blacklisted words here", permission="sudo")
async def list_bl(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(select(BlacklistWord).where(
            BlacklistWord.chat_id == event.chat_id))
        rows = r.scalars().all()
    if not rows:
        await event.edit(Messages.info("No words blacklisted here."))
        return
    await event.edit(
        f"🚫 **Blacklisted** ({len(rows)})\n{SEP_FANCY}\n"
        + "\n".join(f"• `{w.word}`" for w in rows)
    )


@listener(events.NewMessage(incoming=True))
async def _bl_watcher(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None or event.is_private or not event.raw_text:
        return
    me = await event.client.get_me()
    if not await is_admin(event.client, event.chat_id, me.id):
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(BlacklistWord).where(
            BlacklistWord.chat_id == event.chat_id))
        rows = r.scalars().all()
    if not rows:
        return
    text = event.raw_text.lower()
    for row in rows:
        if row.word in text:
            try:
                await event.delete()
            except Exception:
                pass
            return


@command("addblkchat", "Add this chat to blacklist", permission="sudo")
async def add_bl_chat(event):
    ctx = event.ctx
    chat = await event.get_chat()
    name = getattr(chat, "title", None) or getattr(chat, "first_name", "") or ""
    username = getattr(chat, "username", "") or ""
    async with ctx.database.session() as s:
        r = await s.execute(select(BlacklistChat).where(
            BlacklistChat.chat_id == event.chat_id))
        if r.scalar_one_or_none() is None:
            s.add(BlacklistChat(chat_id=event.chat_id, name=name, username=username))
    await event.edit(Messages.success(f"Blacklisted `{name or event.chat_id}`."))


@command("rmblkchat", "Remove this chat from blacklist", permission="sudo")
async def rm_bl_chat(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(select(BlacklistChat).where(
            BlacklistChat.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        if row:
            await s.delete(row)
    await event.edit(Messages.success("Removed from blacklist."))


@command("listblkchat", "List blacklisted chats", permission="sudo")
async def list_bl_chats(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(select(BlacklistChat))
        rows = r.scalars().all()
    if not rows:
        await event.edit(Messages.info("No blacklisted chats."))
        return
    await event.edit(
        f"🚫 **Blacklisted chats** ({len(rows)})\n{SEP_FANCY}\n"
        + "\n".join(f"• `{c.chat_id}` — {c.name or '—'}" for c in rows)
    )
