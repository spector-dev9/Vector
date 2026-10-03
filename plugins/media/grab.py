"""Grab — account-scoped media saver."""
import asyncio
import io
import time
from pathlib import Path

from telethon import events
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

from core.decorators import command, listener
from core.module import ModuleMeta
from utils import Messages, Formatters

META = ModuleMeta(
    name="grab", category="media",
    description="Download or copy any media, including ephemeral.",
    permission="user",
)

VIEW_ONCE = 2147483647
_batch_cooldown = {}
_STATE = {}


def _st(ctx):
    return _STATE.setdefault(ctx.account_id, {"auto": False})


def _ttl(msg):
    if not msg or not msg.media:
        return 0
    return int(getattr(msg.media, "ttl_seconds", 0) or 0)


def _kind(msg):
    if not msg or not msg.media:
        return "none"
    if isinstance(msg.media, MessageMediaPhoto):
        return "photo"
    if isinstance(msg.media, MessageMediaDocument):
        doc = msg.media.document
        mime = (getattr(doc, "mime_type", "") or "").lower()
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("image/"):
            return "photo"
        for a in getattr(doc, "attributes", []) or []:
            n = type(a).__name__
            if n == "DocumentAttributeVideo":
                return "video"
            if n == "DocumentAttributeAudio":
                return "voice" if getattr(a, "voice", False) else "audio"
            if n == "DocumentAttributeSticker":
                return "sticker"
        return "document"
    return "none"


def _label(ttl):
    if ttl == 0:
        return "normal"
    if ttl >= VIEW_ONCE:
        return "view-once"
    return f"self-destruct {ttl}s"


def _fname(msg):
    if not msg or not msg.media:
        return "file"
    doc = getattr(msg.media, "document", None)
    if doc:
        for a in getattr(doc, "attributes", []) or []:
            if getattr(a, "file_name", None):
                safe = a.file_name.replace("/", "_").replace("\\", "_")
                return safe[:180] or "file"
    ext = {"photo": "jpg", "video": "mp4", "audio": "mp3",
           "voice": "ogg", "sticker": "webp", "document": "bin"}.get(_kind(msg), "bin")
    return f"{_kind(msg)}_{msg.id}.{ext}"


async def _download(msg, event, status=None):
    ctx = event.ctx
    target = ctx.paths.sub("downloads") / _fname(msg)
    last = [0.0]

    async def progress(recv, total):
        if not status or not total or time.time() - last[0] < 2:
            return
        last[0] = time.time()
        pct = recv / total * 100
        try:
            await status.edit(
                f"⬇️ `{pct:.0f}%` "
                f"{Formatters.format_size(recv)}/{Formatters.format_size(total)}")
        except Exception:
            pass

    try:
        p = await event.client.download_media(
            msg, file=str(target), progress_callback=progress)
        return Path(p) if p else None
    except Exception:
        return None


@command("grab", "Save replied media to disk")
async def grab(event):
    if not event.is_reply:
        await event.edit(Messages.error("Reply to a message with media."))
        return
    replied = await event.get_reply_message()
    if not replied or _kind(replied) == "none":
        await event.edit(Messages.error("No media."))
        return
    st = await event.edit(Messages.loading(f"Downloading {_fname(replied)}…"))
    p = await _download(replied, event, status=st)
    if not p:
        await event.edit(Messages.error("Download failed."))
        return
    await event.edit(Messages.success(
        f"Saved `{p.name}` · {Formatters.format_size(p.stat().st_size)}"))


@command("grabdm", "Resend replied media to Saved Messages")
async def grabdm(event):
    if not event.is_reply:
        await event.edit(Messages.error("Reply to media."))
        return
    replied = await event.get_reply_message()
    if not replied or _kind(replied) == "none":
        await event.edit(Messages.error("No media."))
        return
    await event.edit(Messages.loading("Copying…"))
    try:
        buf = await event.client.download_media(replied, file=bytes)
        f = io.BytesIO(buf)
        f.name = _fname(replied)
        await event.client.send_file("me", f, force_document=True)
    except Exception as e:
        await event.edit(Messages.error(str(e)))
        return
    await event.edit(Messages.success("Sent to Saved Messages."))


@command("grabinfo", "Inspect replied media")
async def grabinfo(event):
    if not event.is_reply:
        await event.edit(Messages.error("Reply to a message."))
        return
    r = await event.get_reply_message()
    if not r:
        await event.edit(Messages.error("Can't read."))
        return
    await event.edit(
        f"🔍 **Media info**\n"
        f"Type: `{_kind(r)}`\nTTL: `{_ttl(r)}` ({_label(_ttl(r))})\n"
        f"Msg ID: `{r.id}`\nDate: `{r.date}`")


@command(r"grabbatch (\S+)(?:\s+(\d+)-(\d+))?", "Batch download from a channel",
         permission="sudo")
async def grabbatch(event):
    ctx = event.ctx
    now = time.time()
    if now - _batch_cooldown.get((ctx.account_id, event.sender_id), 0) < 60:
        await event.edit(Messages.warning("Cooldown."))
        return
    _batch_cooldown[(ctx.account_id, event.sender_id)] = now
    raw = event.pattern_match.group(1)
    n1, n2 = event.pattern_match.group(2), event.pattern_match.group(3)
    try:
        entity = await event.client.get_entity(raw)
    except Exception as e:
        await event.edit(Messages.error(str(e)))
        return
    kwargs = {"limit": 200}
    if n1 and n2:
        kwargs["min_id"] = int(n1) - 1
        kwargs["max_id"] = int(n2) + 1
    msgs = []
    async for m in event.client.iter_messages(entity, **kwargs):
        if _kind(m) != "none":
            msgs.append(m)
    if not msgs:
        await event.edit(Messages.info("No media found."))
        return
    st = await event.edit(f"📥 Downloading {len(msgs)} files…")
    done = failed = 0
    for i, m in enumerate(msgs, 1):
        p = await _download(m, event)
        if p:
            done += 1
        else:
            failed += 1
        if i % 3 == 0 or i == len(msgs):
            try:
                await st.edit(f"📥 {i}/{len(msgs)} · ✅{done} ❌{failed}")
            except Exception:
                pass
        await asyncio.sleep(0.3)
    await st.edit(Messages.success(f"Saved **{done}** · failed **{failed}**"))


@command(r"autograb(?:\s+(on|off))?", "Auto-save ephemeral media", permission="sudo")
async def autograb(event):
    st = _st(event.ctx)
    arg = (event.pattern_match.group(1) or "").lower()
    if arg:
        st["auto"] = arg == "on"
    state = "🟢 ON" if st["auto"] else "🔴 OFF"
    await event.edit(Messages.info(f"Auto-grab: **{state}**"))


@listener(events.NewMessage(incoming=True))
async def watcher(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None:
        return
    st = _st(ctx)
    if not st["auto"] or not event.media or _ttl(event) == 0:
        return
    try:
        buf = await event.client.download_media(event, file=bytes)
        if not buf:
            return
        f = io.BytesIO(buf)
        f.name = _fname(event)
        await event.client.send_file(
            "me", f,
            caption=f"📥 **Auto-saved** from `{event.sender_id}` "
                    f"({_label(_ttl(event))})",
            force_document=True,
        )
    except Exception:
        pass
