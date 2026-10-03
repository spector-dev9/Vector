"""Save — snapshot profile into a preset."""
import io
import time
from pathlib import Path

from sqlalchemy import select

from core.decorators import command
from core.module import ModuleMeta
from database.models import Preset
from services.telegram import TelegramService
from utils import Messages

META = ModuleMeta(
    name="save", category="account",
    description="Save profile presets, or archive a DP.",
    permission="user", tags=("profile", "preset"),
)


@command(r"save(?:\s+(.*))?", "Save current profile as preset, or a DP")
async def save_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    if arg.lower().startswith("dp"):
        await _save_dp(event, arg)
        return
    await _save_preset(event, arg or "default")


async def _save_preset(event, name):
    ctx = event.ctx
    await event.edit(Messages.loading(f"Saving preset `{name}`…"))
    me = await event.client.get_me()
    svc = TelegramService(event.client)
    full = await svc.full_user(me.id)
    bio = full.full_user.about or ""

    dp_dir = ctx.paths.sub("presets")
    photo_ref = None
    try:
        photos = await event.client.get_profile_photos("me", limit=1)
        if photos:
            target = dp_dir / f"{me.id}_{int(time.time())}.jpg"
            await event.client.download_media(photos[0], file=str(target))
            photo_ref = str(target)
    except Exception:
        pass

    async with ctx.database.session() as s:
        r = await s.execute(
            select(Preset).where(Preset.user_id == me.id, Preset.name == name)
        )
        row = r.scalar_one_or_none()
        if row is None:
            s.add(Preset(
                user_id=me.id, name=name,
                first_name=me.first_name or "",
                last_name=me.last_name or "",
                bio=bio, username=me.username or "",
                photo_reference=photo_ref,
            ))
            action = "created"
        else:
            row.first_name = me.first_name or ""
            row.last_name = me.last_name or ""
            row.bio = bio
            row.username = me.username or ""
            if photo_ref:
                row.photo_reference = photo_ref
            action = "updated"
    await event.edit(Messages.success(
        f"Preset `{name}` **{action}** (dp: {'✅' if photo_ref else '—'})"
    ))


async def _save_dp(event, arg):
    parts = arg.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await event.edit(Messages.error("Usage: `.save dp <n>` (reply)."))
        return
    if not event.is_reply:
        await event.edit(Messages.error("Reply to a user."))
        return
    replied = await event.get_reply_message()
    target = await replied.get_sender()
    n = int(parts[1])
    photos = await event.client.get_profile_photos(target.id)
    if not photos:
        await event.edit(Messages.error("That user has no DPs."))
        return
    if n > len(photos):
        await event.edit(Messages.error(f"Only {len(photos)} available."))
        return
    buf = io.BytesIO()
    await event.client.download_media(photos[n - 1], file=buf)
    buf.seek(0)
    buf.name = f"dp_{target.id}_{n}.jpg"
    await event.client.send_file("me", buf, caption=f"DP #{n} of {target.first_name}")
    await event.edit(Messages.success(f"Saved DP #{n}."))
