"""Welcome."""
from telethon import events
from sqlalchemy import select
from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import Welcome
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="welcome", category="automation",
    description="Greet joining members.",
    permission="sudo",
)


@command(r"savewelcome(?:\s+([\s\S]+))?", "Save welcome (reply for media)",
         permission="sudo")
async def save_welcome(event):
    ctx = event.ctx
    text = (event.pattern_match.group(1) or "").strip()
    media_id = None
    reply = await event.get_reply_message()
    if reply and reply.media:
        try:
            fwd = await reply.forward_to("me")
            media_id = fwd.id
        except Exception:
            media_id = None
        if not text and reply.raw_text:
            text = reply.raw_text
    elif reply and not text:
        text = reply.raw_text or ""
    if not text and not media_id:
        await event.edit(Messages.error("Give text or reply with media."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(Welcome).where(Welcome.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(Welcome(chat_id=event.chat_id, text=text, media_id=media_id, clean=1))
        else:
            row.text = text
            if media_id:
                row.media_id = media_id
    await event.edit(Messages.success("Welcome saved."))


@command("clearwelcome", "Remove welcome", permission="sudo")
async def clear_welcome(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(select(Welcome).where(Welcome.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        if row:
            await s.delete(row)
    await event.edit(Messages.success("Welcome removed."))


@command("listwelcome", "Show current welcome", permission="sudo")
async def list_welcome(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(select(Welcome).where(Welcome.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
    if row is None:
        await event.edit(Messages.info("No welcome configured."))
        return
    await event.edit(
        f"👋 **Welcome here**\n{SEP_FANCY}\n"
        f"media: `{'yes' if row.media_id else 'no'}`\n"
        f"clean: `{'on' if row.clean else 'off'}`\n\n{row.text}"
    )


@command(r"cleanwelcome(?: (on|off))?", "Toggle deleting previous welcome",
         permission="sudo")
async def clean_welcome(event):
    ctx = event.ctx
    arg = (event.pattern_match.group(1) or "").lower()
    async with ctx.database.session() as s:
        r = await s.execute(select(Welcome).where(Welcome.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        if row is None:
            await event.edit(Messages.warning("Save a welcome first."))
            return
        if arg in ("on", "off"):
            row.clean = 1 if arg == "on" else 0
        state = "on" if row.clean else "off"
    await event.edit(Messages.success(f"clean welcome is **{state}**."))


@listener(events.ChatAction())
async def _welcome_send(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None:
        return
    if not (event.user_joined or event.user_added):
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(Welcome).where(Welcome.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
    if row is None:
        return
    user = await event.get_user()
    me = await event.client.get_me()
    if row.clean and row.previous:
        try:
            await event.client.delete_messages(event.chat_id, row.previous)
        except Exception:
            pass
    text = (
        (row.text or "")
        .replace("{mention}", f"[{user.first_name}](tg://user?id={user.id})")
        .replace("{first}", user.first_name or "")
        .replace("{last}", user.last_name or "")
        .replace("{fullname}", f"{user.first_name or ''} {user.last_name or ''}".strip())
        .replace("{username}", f"@{user.username}" if user.username else "")
        .replace("{my_first}", me.first_name or "")
        .replace("{my_fullname}", f"{me.first_name or ''} {me.last_name or ''}".strip())
        .replace("{my_username}", f"@{me.username}" if me.username else "")
    )
    try:
        if row.media_id:
            try:
                msg = await event.client.get_messages("me", ids=row.media_id)
                if msg:
                    sent = await event.reply(text or msg.message, file=msg.media)
                    async with ctx.database.session() as s:
                        r = await s.execute(
                            select(Welcome).where(Welcome.chat_id == event.chat_id))
                        row2 = r.scalar_one_or_none()
                        if row2:
                            row2.previous = sent.id
                    return
            except Exception:
                pass
        sent = await event.reply(text or "👋 welcome!")
        async with ctx.database.session() as s:
            r = await s.execute(select(Welcome).where(Welcome.chat_id == event.chat_id))
            row2 = r.scalar_one_or_none()
            if row2:
                row2.previous = sent.id
    except Exception:
        pass
