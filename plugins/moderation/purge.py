"""Purge."""
import asyncio
from core.decorators import command
from core.module import ModuleMeta
from helpers.telegram.messages import safe_edit
from utils import Messages

META = ModuleMeta(
    name="purge", category="moderation",
    description="Purge messages from reply to now, or your own.",
    permission="sudo",
)


async def _bulk(client, chat_id, ids):
    total = 0
    for i in range(0, len(ids), 100):
        try:
            await client.delete_messages(chat_id, ids[i:i + 100])
            total += len(ids[i:i + 100])
        except Exception:
            pass
    return total


async def _temp(client, chat_id, text, ttl=4):
    try:
        note = await client.send_message(chat_id, text)
        await asyncio.sleep(ttl)
        await note.delete()
    except Exception:
        pass


@command("purge", "Delete from reply to now", permission="sudo")
async def purge(event):
    if not event.is_reply:
        await safe_edit(event, Messages.error("Reply to start message."))
        return
    replied = await event.get_reply_message()
    if replied is None:
        return
    await safe_edit(event, Messages.loading("Purging…"))
    ids = [event.message.id]
    try:
        async for m in event.client.iter_messages(
            event.chat_id, min_id=replied.id - 1,
            max_id=event.message.id, reverse=True,
        ):
            ids.append(m.id)
    except Exception:
        pass
    deleted = await _bulk(event.client, event.chat_id, ids)
    await _temp(event.client, event.chat_id,
                Messages.success(f"Purged {deleted} messages."), ttl=3)


@command(r"purgeme(?:\s+(\d+))?", "Delete your last N messages", permission="sudo")
async def purgeme(event):
    n = int(event.pattern_match.group(1) or 10)
    if not 1 <= n <= 500:
        await safe_edit(event, Messages.error("Number 1–500."))
        return
    await safe_edit(event, Messages.loading(f"Purging {n}…"))
    me = await event.client.get_me()
    ids = [event.message.id]
    try:
        async for m in event.client.iter_messages(event.chat_id, limit=300):
            if m.sender_id == me.id:
                ids.append(m.id)
            if len(ids) >= n + 1:
                break
    except Exception:
        pass
    deleted = await _bulk(event.client, event.chat_id, ids)
    await _temp(event.client, event.chat_id,
                Messages.success(f"Deleted {deleted}."), ttl=3)


@command("del", "Delete replied message", permission="sudo")
async def del_cmd(event):
    if not event.is_reply:
        await safe_edit(event, Messages.error("Reply to a message."))
        return
    replied = await event.get_reply_message()
    if replied is None:
        return
    try:
        await event.client.delete_messages(event.chat_id, [replied.id, event.message.id])
    except Exception:
        pass


@command("delf", "Forward to Saved then delete", permission="sudo")
async def delf(event):
    if not event.is_reply:
        await safe_edit(event, Messages.error("Reply to a message."))
        return
    replied = await event.get_reply_message()
    if replied is None:
        return
    try:
        await replied.forward_to("me")
    except Exception as e:
        await safe_edit(event, Messages.error(str(e)))
        return
    try:
        await event.client.delete_messages(event.chat_id, [replied.id, event.message.id])
    except Exception:
        pass
