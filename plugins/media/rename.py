"""Rename."""
import os
from telethon.tl.types import DocumentAttributeFilename
from telethon.utils import get_attributes
from core.decorators import command
from core.module import ModuleMeta
from helpers.telegram.messages import safe_edit
from utils import Messages

META = ModuleMeta(
    name="rename", category="media",
    description="Rename replied file and re-upload.",
    permission="user",
)


@command(r"rnup(?:\s+-f)?\s+([\s\S]+)", "Rename + upload replied file")
async def rnup(event):
    ctx = event.ctx
    reply = await event.get_reply_message()
    if reply is None or not (reply.document or reply.photo):
        await safe_edit(event, Messages.error("Reply to a file."))
        return
    raw = event.raw_text
    force_doc = "-f " in raw
    new_name = event.pattern_match.group(1).strip()
    if not new_name:
        await safe_edit(event, Messages.error("Give a new filename."))
        return
    status = await event.edit(Messages.loading(f"Downloading as `{new_name}`…"))
    tmp_dir = ctx.paths.sub("rename_tmp")
    fpath = await event.client.download_media(reply, file=str(tmp_dir / new_name))
    if not fpath:
        await safe_edit(event, Messages.error("Download failed."))
        return
    try:
        attributes, mime_type = get_attributes(fpath)
        attributes = [a for a in attributes
                      if not isinstance(a, DocumentAttributeFilename)]
        attributes.append(DocumentAttributeFilename(file_name=os.path.basename(fpath)))
        await event.client.send_file(
            event.chat_id, fpath, attributes=attributes,
            force_document=force_doc or bool(reply.document),
            supports_streaming=not force_doc,
            caption=f"`{os.path.basename(fpath)}`",
        )
    finally:
        try:
            os.remove(fpath)
        except Exception:
            pass
    await status.delete()
