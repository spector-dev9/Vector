"""Per-account thumbnail."""
import io
from PIL import Image
from core.decorators import command
from core.module import ModuleMeta
from helpers.telegram.messages import safe_edit
from utils import Messages

META = ModuleMeta(
    name="thumbnail", category="media",
    description="Save / show / clear a default thumbnail.",
    permission="user",
)


def _thumb_path(ctx):
    return ctx.paths.file("thumb.jpg")


@command("savethumb", "Save replied media as thumbnail")
async def save_thumb(event):
    ctx = event.ctx
    reply = await event.get_reply_message()
    if reply is None or not reply.media:
        await safe_edit(event, Messages.error("Reply to an image/video."))
        return
    await safe_edit(event, Messages.loading("Saving thumbnail…"))
    buf = await event.client.download_media(reply, file=bytes)
    try:
        with Image.open(io.BytesIO(buf)) as img:
            img.convert("RGB").save(_thumb_path(ctx), "JPEG")
    except Exception as e:
        await safe_edit(event, Messages.error(str(e)))
        return
    await safe_edit(event, Messages.success("Thumbnail saved."))


@command("clearthumb", "Delete saved thumbnail")
async def clear_thumb(event):
    ctx = event.ctx
    p = _thumb_path(ctx)
    if p.exists():
        p.unlink()
        await safe_edit(event, Messages.success("Thumbnail cleared."))
    else:
        await safe_edit(event, Messages.info("No thumbnail saved."))


@command("getthumb", "Show current thumbnail")
async def get_thumb(event):
    ctx = event.ctx
    p = _thumb_path(ctx)
    if not p.exists():
        await safe_edit(event, Messages.info("No thumbnail saved."))
        return
    await event.client.send_file(event.chat_id, str(p),
                                 caption="Current thumbnail",
                                 force_document=False)
