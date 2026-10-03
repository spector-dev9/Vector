"""Ghost — per account."""
import asyncio
from telethon import events
from core.decorators import command, listener
from core.module import ModuleMeta
from utils import Messages

META = ModuleMeta(
    name="ghost", category="automation",
    description="Auto-delete your own outgoing messages.",
    permission="user",
)

_STATE = {}


def _st(ctx):
    return _STATE.setdefault(ctx.account_id,
                             {"enabled": False, "delay": 30, "skip": set()})


@command(r"ghoston(?:\s+(\d+))?", "Enable ghost mode")
async def ghoston(event):
    ctx = event.ctx
    delay = int(event.pattern_match.group(1) or 30)
    if delay < 5:
        await event.edit(Messages.error("Minimum 5s."))
        return
    st = _st(ctx)
    st["enabled"] = True
    st["delay"] = delay
    try:
        note = await event.respond(Messages.success(f"👻 Ghost ON — {delay}s"))
        st["skip"].add(note.id)
        await asyncio.sleep(3)
        await note.delete()
    except Exception:
        pass


@command("ghostoff", "Disable ghost mode")
async def ghostoff(event):
    ctx = event.ctx
    st = _st(ctx)
    st["enabled"] = False
    try:
        note = await event.respond(Messages.success("👻 Ghost OFF"))
        st["skip"].add(note.id)
        await asyncio.sleep(3)
        await note.delete()
    except Exception:
        pass


@command("ghost", "Ghost status")
async def ghost_status(event):
    st = _st(event.ctx)
    if st["enabled"]:
        await event.edit(Messages.info(f"👻 ON — {st['delay']}s"))
    else:
        await event.edit(Messages.info("👻 OFF"))


@listener(events.NewMessage(outgoing=True))
async def watcher(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None:
        return
    st = _st(ctx)
    if not st["enabled"]:
        return
    text = event.raw_text or ""
    if text.startswith("."):
        return
    try:
        me = await event.client.get_me()
        if event.chat_id == me.id:
            return
    except Exception:
        pass
    if event.message.id in st["skip"]:
        st["skip"].discard(event.message.id)
        return
    delay = st["delay"]
    chat_id = event.chat_id
    msg_id = event.message.id

    async def later():
        await asyncio.sleep(delay)
        try:
            await event.client.delete_messages(chat_id, [msg_id])
        except Exception:
            pass

    asyncio.create_task(later())
