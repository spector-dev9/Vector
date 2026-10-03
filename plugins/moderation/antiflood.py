"""Antiflood — per account."""
import time
from collections import defaultdict, deque

from telethon import events
from sqlalchemy import select
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights

from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import AntifloodSetting
from helpers.telegram.admins import is_admin
from utils import Messages

META = ModuleMeta(
    name="antiflood", category="moderation",
    description="Auto-mute users who flood a chat.",
    permission="sudo",
)

_buckets: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=40))
WINDOW = 6
MUTE_SECONDS = 60


@command(r"setflood(?:\s+(\d+))?", "Set anti-flood limit (0 disables)", permission="sudo")
async def setflood(event):
    ctx = event.ctx
    n = int(event.pattern_match.group(1) or 0)
    async with ctx.database.session() as s:
        r = await s.execute(select(AntifloodSetting).where(
            AntifloodSetting.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(AntifloodSetting(chat_id=event.chat_id, limit=n))
        else:
            row.limit = n
    if n == 0:
        await event.edit(Messages.success("Anti-flood disabled."))
    else:
        await event.edit(Messages.success(
            f"Anti-flood: {n} msgs / {WINDOW}s → {MUTE_SECONDS}s mute."
        ))


@listener(events.NewMessage(incoming=True))
async def _watch(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None or event.is_private or not event.sender_id:
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(AntifloodSetting).where(
            AntifloodSetting.chat_id == event.chat_id))
        row = r.scalar_one_or_none()
    if row is None or row.limit <= 0:
        return
    me = await event.client.get_me()
    if not await is_admin(event.client, event.chat_id, me.id):
        return
    trigger = row.limit
    now = time.time()
    bucket = _buckets[(ctx.account_id, event.chat_id, event.sender_id)]
    bucket.append(now)
    while bucket and now - bucket[0] > WINDOW:
        bucket.popleft()
    if len(bucket) < trigger:
        return
    try:
        await event.client(EditBannedRequest(
            event.chat_id, event.sender_id,
            ChatBannedRights(until_date=int(now) + MUTE_SECONDS, send_messages=True),
        ))
    except Exception:
        return
    bucket.clear()
    try:
        await event.reply(f"🚫 Muted for {MUTE_SECONDS}s (flooding).")
    except Exception:
        pass
