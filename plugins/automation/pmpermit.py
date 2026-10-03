"""PMPermit — DB-backed enable flag."""
from datetime import datetime

from telethon import Button, events
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from sqlalchemy import select

from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import PmPermit, BotFlag
from helpers.telegram.admins import get_user_and_reason, mention
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="pmpermit", category="automation",
    description="Gate incoming PMs behind an approve list.",
    permission="sudo",
)

_FLAG = "pmpermit_enabled"


async def _enabled(ctx):
    async with ctx.database.session() as s:
        r = await s.execute(select(BotFlag).where(BotFlag.key == _FLAG))
        row = r.scalar_one_or_none()
        return row is not None and row.value == "1"


async def _set_enabled(ctx, value):
    async with ctx.database.session() as s:
        r = await s.execute(select(BotFlag).where(BotFlag.key == _FLAG))
        row = r.scalar_one_or_none()
        v = "1" if value else "0"
        if row is None:
            s.add(BotFlag(key=_FLAG, value=v))
        else:
            row.value = v


@command(r"pmguard(?: (on|off))?", "Turn PM permit on/off", permission="sudo")
async def pmguard(event):
    ctx = event.ctx
    arg = (event.pattern_match.group(1) or "").lower()
    if arg in ("on", "off"):
        await _set_enabled(ctx, arg == "on")
    state = "🟢 ON" if await _enabled(ctx) else "🔴 OFF"
    await event.edit(Messages.info(f"PM guard: **{state}**"))


@command(r"approve(?:\s+(.+))?", "Approve a user to DM", permission="sudo")
async def approve(event):
    ctx = event.ctx
    if event.is_private:
        target = await event.get_chat()
        reason = event.pattern_match.group(1) or "unspecified"
    else:
        target, reason = await get_user_and_reason(event, 1)
        reason = reason or "unspecified"
    if target is None:
        await event.edit(Messages.error("Couldn't resolve."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(PmPermit).where(PmPermit.user_id == target.id))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(PmPermit(
                user_id=target.id,
                first_name=getattr(target, "first_name", "") or "",
                username=getattr(target, "username", "") or "",
                reason=reason,
                date=datetime.now().strftime("%Y-%m-%d"),
            ))
        else:
            row.reason = reason
    await event.edit(Messages.success(
        f"Approved {await mention(target)} — `{reason}`."))


@command(r"disapprove(?:\s+(.+))?", "Disapprove a user", permission="sudo")
async def disapprove(event):
    ctx = event.ctx
    if event.is_private:
        target = await event.get_chat()
    else:
        target, _ = await get_user_and_reason(event, 1)
    if target is None:
        await event.edit(Messages.error("Couldn't resolve."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(PmPermit).where(PmPermit.user_id == target.id))
        row = r.scalar_one_or_none()
        if row:
            await s.delete(row)
    await event.edit(Messages.success(f"Disapproved {await mention(target)}."))


@command("listapproved", "List approved DMs", permission="sudo")
async def list_approved(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(select(PmPermit))
        rows = r.scalars().all()
    if not rows:
        await event.edit(Messages.info("No approved users."))
        return
    lines = [f"✅ **Approved ({len(rows)})**", SEP_FANCY]
    for row in rows[:50]:
        lines.append(f"• `{row.user_id}` — {row.first_name or '—'} — _{row.reason}_")
    await event.edit("\n".join(lines))


@command(r"block(?:\s+(.+))?", "Block a user", permission="sudo")
async def block(event):
    if event.is_private:
        target = await event.get_chat()
    else:
        target, _ = await get_user_and_reason(event, 1)
    if target is None:
        await event.edit(Messages.error("Couldn't resolve."))
        return
    try:
        await event.client(BlockRequest(target.id))
        await event.edit(Messages.success(f"Blocked {await mention(target)}."))
    except Exception as e:
        await event.edit(Messages.error(str(e)))


@command(r"unblock(?:\s+(.+))?", "Unblock a user", permission="sudo")
async def unblock(event):
    if event.is_private:
        target = await event.get_chat()
    else:
        target, _ = await get_user_and_reason(event, 1)
    if target is None:
        await event.edit(Messages.error("Couldn't resolve."))
        return
    try:
        await event.client(UnblockRequest(target.id))
        await event.edit(Messages.success(f"Unblocked {await mention(target)}."))
    except Exception as e:
        await event.edit(Messages.error(str(e)))


@listener(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def _permit(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None:
        return
    if not await _enabled(ctx):
        return
    sender = await event.get_sender()
    if sender is None or getattr(sender, "bot", False):
        return
    me = await event.client.get_me()
    if sender.id == me.id:
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(PmPermit).where(PmPermit.user_id == sender.id))
        approved = r.scalar_one_or_none()
    if approved is not None:
        return
    text = f"👋 Hi {sender.first_name}!\n\nPick a reason below."
    buttons = [[
        Button.inline("Enquire", data=f"pm:enq:{sender.id}"),
        Button.inline("Request", data=f"pm:req:{sender.id}"),
        Button.inline("Chat", data=f"pm:cht:{sender.id}"),
    ], [
        Button.inline("Spam", data=f"pm:spm:{sender.id}"),
    ]]
    try:
        await event.reply(text, buttons=buttons)
    except Exception:
        pass


@listener(events.CallbackQuery(pattern=rb"^pm:"))
async def _permit_cb(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None:
        return
    try:
        _, action, uid = event.data.decode().split(":")
        uid = int(uid)
    except Exception:
        await event.answer()
        return
    if event.sender_id != uid:
        await event.answer("Not your call.", alert=True)
        return
    labels = {"enq": "Enquiry logged.", "req": "Request logged.",
              "cht": "Chat logged.", "spm": "Blocked."}
    await event.answer(labels.get(action, "Noted."), alert=False)
    if action == "spm":
        try:
            await event.client(BlockRequest(uid))
        except Exception:
            pass
        try:
            await event.edit("🚫 Blocked.")
        except Exception:
            pass
        return
    try:
        await event.edit("✅ Noted.")
    except Exception:
        pass
