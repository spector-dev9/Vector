"""Clone — replicate another profile."""
import io

from telethon import functions

from core.decorators import command
from core.module import ModuleMeta
from helpers.telegram.users import resolve_user
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="clone", category="account",
    description="Clone name + bio + photo from another user.",
    permission="user",
)


@command(r"clone(?:\s+(\S+))?", "Clone another profile")
async def clone(event):
    arg = event.pattern_match.group(1)
    target = await resolve_user(event.client, arg) if arg else None
    if target is None and event.is_reply:
        replied = await event.get_reply_message()
        target = await replied.get_sender()
    if target is None:
        await event.edit(Messages.error("Give @username, id, or reply."))
        return
    me = await event.client.get_me()
    if getattr(target, "id", None) == me.id:
        await event.edit(Messages.error("That's you."))
        return
    await event.edit(Messages.loading("Cloning…"))
    first = (getattr(target, "first_name", "") or "Cloned")[:64]
    last = (getattr(target, "last_name", "") or "")[:64]
    bio = ""
    try:
        full = await event.client(functions.users.GetFullUserRequest(id=target.id))
        bio = (full.full_user.about or "")[:70]
    except Exception:
        pass
    try:
        await event.client(functions.account.UpdateProfileRequest(
            first_name=first, last_name=last, about=bio,
        ))
    except Exception as e:
        await event.edit(Messages.error(str(e)))
        return
    photo_status = "not cloned"
    try:
        photos = await event.client.get_profile_photos(target)
        if photos:
            existing = await event.client.get_profile_photos("me")
            if existing:
                try:
                    await event.client(
                        functions.photos.DeletePhotosRequest(id=list(existing))
                    )
                except Exception:
                    pass
            buf = await event.client.download_media(photos[0], file=bytes)
            f = io.BytesIO(buf)
            f.name = "clone.jpg"
            uploaded = await event.client.upload_file(f)
            await event.client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
            photo_status = "cloned"
    except Exception as e:
        photo_status = f"failed ({e})"
    await event.edit(
        f"👤 **Cloned**\n{SEP_FANCY}\n"
        f"**Name:** {first} {last}\n"
        f"**Bio:** {bio or '—'}\n"
        f"**Photo:** {photo_status}"
    )
