"""Presets — list, revert, delete."""
from pathlib import Path

from sqlalchemy import select
from telethon import functions

from core.decorators import command
from core.module import ModuleMeta
from database.models import Preset
from utils import Messages

META = ModuleMeta(
    name="presets", category="account",
    description="List, revert and delete saved profile presets.",
    permission="user",
)


@command("presets", "List saved presets")
async def list_handler(event):
    ctx = event.ctx
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(
            select(Preset).where(Preset.user_id == me.id)
            .order_by(Preset.updated_at.desc())
        )
        rows = r.scalars().all()
    if not rows:
        await event.edit(Messages.info("No presets saved."))
        return
    lines = ["🗂 **Presets**\n"]
    for p in rows:
        dp = "✅" if p.photo_reference and Path(p.photo_reference).exists() else "—"
        lines.append(f"• `{p.name}` · bio={len(p.bio or '')}c · dp={dp}")
    await event.edit("\n".join(lines))


@command(r"revert(?:\s+(.*))?", "Revert to a saved preset")
async def revert_handler(event):
    ctx = event.ctx
    name = (event.pattern_match.group(1) or "default").strip()
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Preset).where(
            Preset.user_id == me.id, Preset.name == name))
        row = r.scalar_one_or_none()
    if row is None:
        await event.edit(Messages.error(f"Preset `{name}` not found."))
        return
    await event.edit(Messages.loading(f"Reverting to `{name}`…"))
    await event.client(functions.account.UpdateProfileRequest(
        first_name=(row.first_name or "Me")[:64],
        last_name=(row.last_name or "")[:64],
        about=(row.bio or "")[:70],
    ))
    if row.photo_reference and Path(row.photo_reference).exists():
        try:
            photos = await event.client.get_profile_photos("me")
            if photos:
                await event.client(functions.photos.DeletePhotosRequest(id=list(photos)))
            uploaded = await event.client.upload_file(row.photo_reference)
            await event.client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
        except Exception:
            pass
    await event.edit(Messages.success(f"Reverted to `{name}`."))


@command(r"presetdel(?:\s+(.*))?", "Delete a preset")
async def del_handler(event):
    ctx = event.ctx
    name = (event.pattern_match.group(1) or "default").strip()
    me = await event.client.get_me()
    async with ctx.database.session() as s:
        r = await s.execute(select(Preset).where(
            Preset.user_id == me.id, Preset.name == name))
        row = r.scalar_one_or_none()
        if row is None:
            await event.edit(Messages.error(f"`{name}` not found."))
            return
        dp = row.photo_reference
        await s.delete(row)
    if dp and Path(dp).exists():
        try:
            Path(dp).unlink()
        except Exception:
            pass
    await event.edit(Messages.success(f"Deleted preset `{name}`."))
