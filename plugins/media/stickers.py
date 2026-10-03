"""Stickers — kang via @Stickers bot."""
import io
import os
from PIL import Image
from telethon.errors import YouBlockedUserError
from telethon.tl.functions.contacts import UnblockRequest
from telethon.tl.types import DocumentAttributeSticker

from core.decorators import command
from core.module import ModuleMeta
from helpers.telegram.messages import safe_edit
from utils import Messages

META = ModuleMeta(
    name="stickers", category="media",
    description="Kang stickers/images/videos into your pack.",
    permission="user",
)

STICKER_BOT = "@Stickers"


def _resize(photo_path, out):
    with Image.open(photo_path) as img:
        if img.width > img.height:
            ratio = 512 / img.width
            img = img.resize((512, max(1, int(img.height * ratio))))
        else:
            ratio = 512 / img.height
            img = img.resize((max(1, int(img.width * ratio)), 512))
        img.save(out, "PNG")


@command(r"kang(?:\s+(.+))?", "Kang replied media")
async def kang(event):
    ctx = event.ctx
    reply = await event.get_reply_message()
    if reply is None or not reply.media:
        await event.edit(Messages.error("Reply to a sticker, image, or video."))
        return
    arg = (event.pattern_match.group(1) or "").strip()
    emoji, pack_suffix = "🤔", "1"
    if arg:
        parts = arg.split(maxsplit=1)
        first = parts[0]
        if len(first) and not first.isdigit() and not first.isalpha():
            emoji = first
            pack_suffix = parts[1] if len(parts) > 1 else "1"
        elif first.isdigit():
            pack_suffix = first
            if len(parts) > 1:
                emoji = parts[1]
        else:
            emoji = first
    me = await event.client.get_me()
    user_tag = me.username or f"user{me.id}"
    pack_name = f"vector_{user_tag}_{pack_suffix}"
    status = await event.edit(Messages.loading("Kanging…"))
    is_video = bool(reply.document and reply.document.mime_type == "video/webm")
    is_animated = bool(reply.document and reply.document.mime_type == "application/x-tgsticker")
    tmp_dir = ctx.paths.sub("sticker_tmp")
    fpath = await event.client.download_media(reply, file=str(tmp_dir / "kang"))
    if not fpath:
        await safe_edit(event, Messages.error("Download failed."))
        return
    try:
        async with event.client.conversation(STICKER_BOT) as conv:
            try:
                await conv.send_message("/cancel")
            except YouBlockedUserError:
                await event.client(UnblockRequest(STICKER_BOT))
                await conv.send_message("/cancel")
            await conv.get_response()
            await conv.send_message("/addsticker")
            await conv.get_response()
            await conv.send_message(pack_name)
            resp = await conv.get_response()
            if "50" in resp.message or "120" in resp.message or "Invalid" in resp.message:
                await conv.send_message("/cancel")
                await conv.get_response()
                await conv.send_message("/newpack")
                await conv.get_response()
                await conv.send_message(f"{user_tag} vol.{pack_suffix}")
                await conv.get_response()
            if is_animated or is_video:
                await conv.send_file(fpath, force_document=True)
            else:
                png = io.BytesIO()
                _resize(fpath, png)
                png.name = "sticker.png"
                await conv.send_file(png, force_document=True)
            resp = await conv.get_response()
            if "Unsupported" in resp.message or "Sorry" in resp.message:
                await safe_edit(event, Messages.error(resp.message))
                return
            await conv.send_message(emoji)
            await conv.get_response()
            await conv.send_message("/publish")
            try:
                await conv.get_response(timeout=2)
                await conv.send_message(f"{user_tag} vol.{pack_suffix}")
                await conv.get_response()
            except Exception:
                pass
            await conv.send_message("/skip")
            await conv.get_response()
            await conv.send_message(pack_name)
            await conv.get_response()
    except Exception as e:
        await safe_edit(event, Messages.error(str(e)))
        return
    finally:
        try:
            os.remove(fpath)
        except Exception:
            pass
    await safe_edit(event, Messages.success(
        f"Added to pack `{pack_name}` (emoji {emoji})."))


@command("stkinfo", "Sticker pack info")
async def stkinfo(event):
    reply = await event.get_reply_message()
    if not reply or not reply.document:
        await event.edit(Messages.error("Reply to a sticker."))
        return
    info = None
    for a in reply.document.attributes:
        if isinstance(a, DocumentAttributeSticker):
            info = a
            break
    if info is None:
        await event.edit(Messages.error("Not a sticker."))
        return
    pack = info.stickerset
    if pack is None:
        await event.edit(Messages.info("This sticker isn't in any pack."))
        return
    await event.edit(
        f"📦 **{getattr(pack, 'title', 'pack')}**\n"
        f"`short_name`: `{getattr(pack, 'short_name','')}`\n"
        f"`id`: `{getattr(pack, 'id', '')}`\n"
        f"`emoji`: {info.alt or '—'}")
