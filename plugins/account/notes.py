"""Notes."""
from sqlalchemy import select

from core.decorators import command
from core.module import ModuleMeta
from database.models import Note
from helpers.telegram.messages import safe_edit
from utils import Messages

META = ModuleMeta(
    name="notes", category="account",
    description="Save and retrieve named text snippets.",
    permission="user",
)


@command(r"note (\w+)(?:\s+(.+))?", "Save a note")
async def note(event):
    ctx = event.ctx
    name = event.pattern_match.group(1)
    inline = event.pattern_match.group(2)
    if inline:
        content = inline
    elif event.is_reply:
        replied = await event.get_reply_message()
        content = replied.raw_text or ""
        if not content:
            await safe_edit(event, Messages.error("Replied has no text."))
            return
    else:
        await safe_edit(event, Messages.error("Usage: `.note <name> <text>` or reply."))
        return
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Note).where(
            Note.user_id == me.id, Note.name == name))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(Note(user_id=me.id, name=name, content=content))
            action = "saved"
        else:
            row.content = content
            action = "updated"
    await safe_edit(event, Messages.success(f"Note `{name}` {action}."))


@command(r"get (\w+)", "Retrieve a note")
async def get(event):
    ctx = event.ctx
    name = event.pattern_match.group(1)
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Note).where(
            Note.user_id == me.id, Note.name == name))
        row = r.scalar_one_or_none()
    if row is None:
        await safe_edit(event, Messages.error(f"Note `{name}` not found."))
        return
    await safe_edit(event, f"📝 **{name}**\n\n{row.content}")


@command("notes", "List notes")
async def notes(event):
    ctx = event.ctx
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Note).where(Note.user_id == me.id).order_by(Note.name))
        rows = r.scalars().all()
    if not rows:
        await safe_edit(event, Messages.info("No notes."))
        return
    lines = ["📝 **Notes**\n"]
    for r in rows:
        p = r.content[:40] + "…" if len(r.content) > 40 else r.content
        lines.append(f"• `{r.name}` — {p}")
    await safe_edit(event, "\n".join(lines))


@command(r"notedel (\w+)", "Delete a note")
async def notedel(event):
    ctx = event.ctx
    name = event.pattern_match.group(1)
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Note).where(
            Note.user_id == me.id, Note.name == name))
        row = r.scalar_one_or_none()
        if row is None:
            await safe_edit(event, Messages.error(f"`{name}` not found."))
            return
        await s.delete(row)
    await safe_edit(event, Messages.success(f"Deleted `{name}`."))
