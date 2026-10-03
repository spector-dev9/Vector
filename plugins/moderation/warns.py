"""Warns."""
from sqlalchemy import select

from core.decorators import command
from core.module import ModuleMeta
from database.models import Warn, WarnSetting
from helpers.telegram.admins import get_user_and_reason, mention
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="warns", category="moderation",
    description="Warn / unwarn users. Auto-ban or kick on limit.",
    permission="sudo",
)


async def _setting(ctx, chat_id):
    async with ctx.database.session() as s:
        r = await s.execute(select(WarnSetting).where(WarnSetting.chat_id == chat_id))
        row = r.scalar_one_or_none()
        if row is None:
            row = WarnSetting(chat_id=chat_id, limit=3, soft=0)
            s.add(row)
            await s.flush()
        return row


@command(r"warn(?:\s+([\s\S]+))?", "Warn a user", permission="sudo")
async def warn(event):
    ctx = event.ctx
    user, reason = await get_user_and_reason(event)
    if user is None:
        await event.edit(Messages.error("Reply or give a user."))
        return
    reason = (reason or "no reason").strip()
    setting = await _setting(ctx, event.chat_id)
    async with ctx.database.session() as s:
        r = await s.execute(select(Warn).where(
            Warn.user_id == user.id, Warn.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        if row is None:
            row = Warn(user_id=user.id, chat_id=event.chat_id, count=1, reasons=reason)
            s.add(row)
        else:
            row.count += 1
            row.reasons = (row.reasons + "\n" + reason).strip()
        count = row.count

    if count >= setting.limit:
        try:
            if setting.soft:
                await event.client.kick_participant(event.chat_id, user.id)
                action = "kicked"
            else:
                from telethon.tl.functions.channels import EditBannedRequest
                from telethon.tl.types import ChatBannedRights
                await event.client(EditBannedRequest(
                    event.chat_id, user.id,
                    ChatBannedRights(until_date=None, view_messages=True),
                ))
                action = "banned"
        except Exception as e:
            await event.edit(Messages.warning(f"Limit hit but couldn't act: {e}"))
            return
        async with ctx.database.session() as s:
            r = await s.execute(select(Warn).where(
                Warn.user_id == user.id, Warn.chat_id == event.chat_id))
            for row in r.scalars().all():
                await s.delete(row)
        await event.edit(Messages.success(
            f"{await mention(user)} reached {setting.limit} warnings — **{action}**."
        ))
        return
    await event.edit(
        f"⚠️ **{await mention(user)}** · warn {count}/{setting.limit}\n"
        f"{SEP_FANCY}\n_Reason:_ {reason}"
    )


@command("warns", "List warns for replied user", permission="sudo")
async def warns(event):
    ctx = event.ctx
    user, _ = await get_user_and_reason(event)
    if user is None:
        await event.edit(Messages.error("Reply to a user."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(Warn).where(
            Warn.user_id == user.id, Warn.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
    if row is None:
        await event.edit(Messages.info("No warns."))
        return
    setting = await _setting(ctx, event.chat_id)
    await event.edit(
        f"**{await mention(user)}** · {row.count}/{setting.limit}\n"
        f"{SEP_FANCY}\n{row.reasons or '_no reasons_'}"
    )


@command("resetwarns", "Reset warns of replied user", permission="sudo")
async def reset_warns(event):
    ctx = event.ctx
    user, _ = await get_user_and_reason(event)
    if user is None:
        await event.edit(Messages.error("Reply to a user."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(Warn).where(
            Warn.user_id == user.id, Warn.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        if row:
            await s.delete(row)
    await event.edit(Messages.success("Warns cleared."))


@command(r"setwarnlimit(?:\s+(\d+))?", "Set warn limit", permission="sudo")
async def set_warn_limit(event):
    ctx = event.ctx
    n = int(event.pattern_match.group(1) or 3)
    async with ctx.database.session() as s:
        r = await s.execute(
            select(WarnSetting).where(WarnSetting.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(WarnSetting(chat_id=event.chat_id, limit=n, soft=0))
        else:
            row.limit = n
    await event.edit(Messages.success(f"Warn limit set to **{n}**."))


@command(r"setwarnstrength(?:\s+(ban|kick))?", "Set action on warn limit",
         permission="sudo")
async def set_warn_strength(event):
    ctx = event.ctx
    arg = (event.pattern_match.group(1) or "").lower()
    if arg not in ("ban", "kick"):
        await event.edit(Messages.error("Usage: `.setwarnstrength ban|kick`"))
        return
    async with ctx.database.session() as s:
        r = await s.execute(
            select(WarnSetting).where(WarnSetting.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        soft = 1 if arg == "kick" else 0
        if row is None:
            s.add(WarnSetting(chat_id=event.chat_id, limit=3, soft=soft))
        else:
            row.soft = soft
    await event.edit(Messages.success(f"On limit: **{arg}**."))
