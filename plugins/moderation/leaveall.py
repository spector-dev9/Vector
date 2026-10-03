""".leavescan / .leaveall."""
import asyncio
import io
import time
from datetime import datetime

from telethon import functions
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel, Chat, InputUserSelf

from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="leaveall", category="moderation",
    description="Save chat links and mass-leave channels/groups.",
    permission="sudo",
)

LEAVE_DELAY = 1.3
COOLDOWN = 120
_last_run = {}


def _is_broadcast(e):
    return isinstance(e, Channel) and getattr(e, "broadcast", False)


def _is_super(e):
    return isinstance(e, Channel) and not getattr(e, "broadcast", False)


def _is_basic(e):
    return isinstance(e, Chat)


def _matches(e, filt):
    if filt == "channels":
        return _is_broadcast(e)
    if filt == "groups":
        return _is_super(e) or _is_basic(e)
    if filt == "supergroups":
        return _is_super(e)
    if filt == "basic":
        return _is_basic(e)
    return _is_broadcast(e) or _is_super(e) or _is_basic(e)


def _type(e):
    if _is_broadcast(e):
        return "channel"
    if _is_super(e):
        return "supergroup"
    if _is_basic(e):
        return "group"
    return "other"


async def _plan(client, filt):
    out = []
    async for d in client.iter_dialogs():
        e = d.entity
        if e and _matches(e, filt):
            out.append({"id": e.id, "title": getattr(e, "title", "—"),
                        "username": getattr(e, "username", None),
                        "type": _type(e), "entity": e})
    return out


async def _save_backup(client, plan, filt):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    lines = ["# VECTOR left-chats backup",
             f"# {datetime.now().isoformat()}",
             f"# filter: {filt}",
             f"# total: {len(plan)}", ""]
    for i, x in enumerate(plan, 1):
        u = f"@{x['username']}" if x["username"] else ""
        link = f"https://t.me/{x['username']}" if x["username"] else ""
        lines.append(f"{i:>3}. [{x['type']}] {x['title']} | id={x['id']} | {u} | {link}")
    buf = io.BytesIO("\n".join(lines).encode("utf-8"))
    buf.name = f"left_{ts}.txt"
    await client.send_file("me", buf,
                           caption=f"📋 {len(plan)} entries · filter `{filt}`",
                           force_document=True)
    return buf.name


@command(r"leavescan(?:\s+(\w+))?", "Preview leave targets", permission="sudo")
async def leavescan(event):
    filt = (event.pattern_match.group(1) or "all").lower()
    if filt not in ("all", "channels", "groups", "supergroups", "basic"):
        await event.edit(Messages.error("Filter: all/channels/groups/supergroups/basic"))
        return
    await event.edit(Messages.loading("Scanning…"))
    plan = await _plan(event.client, filt)
    if not plan:
        await event.edit(Messages.info("No matching chats."))
        return
    lines = [f"📊 **Preview** `{filt}` · {len(plan)} chat(s)", SEP_FANCY]
    for i, x in enumerate(plan[:30], 1):
        lines.append(f"{i}. [{x['type']}] {x['title'][:40]} @{x['username'] or '—'}")
    if len(plan) > 30:
        lines.append(f"…+{len(plan)-30} more")
    await event.edit("\n".join(lines))


@command(r"leaveall(?:\s+(\w+))?", "Save links and leave all", permission="sudo")
async def leaveall(event):
    arg = (event.pattern_match.group(1) or "all").lower()
    save_only = arg == "save"
    filt = "all" if save_only else arg
    if filt not in ("all", "channels", "groups", "supergroups", "basic"):
        await event.edit(Messages.error(
            "Filter: all/channels/groups/supergroups/basic/save"))
        return
    now = time.time()
    ctx = event.ctx
    run_key = (ctx.account_id, event.sender_id)
    wait = COOLDOWN - (now - _last_run.get(run_key, 0))
    if wait > 0:
        await event.edit(Messages.warning(f"Cooldown {int(wait)}s."))
        return
    await event.edit(Messages.loading("Scanning…"))
    plan = await _plan(event.client, filt)
    if not plan:
        await event.edit(Messages.info("No matching chats."))
        return
    _last_run[run_key] = now
    fname = await _save_backup(event.client, plan, filt)
    if save_only:
        await event.edit(Messages.success(f"Saved {len(plan)} entries as `{fname}`."))
        return
    st = await event.edit(f"🚪 Leaving {len(plan)} chats…")
    left = failed = 0
    for i, x in enumerate(plan, 1):
        try:
            if _is_basic(x["entity"]):
                await event.client(functions.messages.DeleteChatUserRequest(
                    chat_id=x["entity"].id, user_id=InputUserSelf()))
            else:
                await event.client(functions.channels.LeaveChannelRequest(
                    channel=x["entity"]))
            left += 1
        except FloodWaitError as e:
            await asyncio.sleep(int(e.seconds) + 3)
            try:
                if _is_basic(x["entity"]):
                    await event.client(functions.messages.DeleteChatUserRequest(
                        chat_id=x["entity"].id, user_id=InputUserSelf()))
                else:
                    await event.client(functions.channels.LeaveChannelRequest(
                        channel=x["entity"]))
                left += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        if i % 3 == 0 or i == len(plan):
            try:
                await st.edit(f"🚪 {i}/{len(plan)} · ✅{left} ❌{failed}")
            except Exception:
                pass
        await asyncio.sleep(LEAVE_DELAY)
    await st.edit(Messages.success(
        f"**Done** — left {left} · failed {failed}\n_Backup:_ `{fname}`"
    ))
