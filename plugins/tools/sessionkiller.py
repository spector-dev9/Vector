"""SessionKiller — polls for new sessions, kills them."""
import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from telethon.tl.functions.account import (
    GetAuthorizationsRequest,
    ResetAuthorizationRequest,
)

from core.decorators import command
from core.logger import setup_logger
from core.module import ModuleMeta
from database.models import BotFlag
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="sessionkiller", category="tools",
    description="Poll for new sessions; kill them and warn you.",
    permission="sudo",
)

logger = setup_logger("VECTOR.sessionkiller")

_ENABLED_KEY = "sessionkiller_enabled"
_KNOWN_KEY = "sessionkiller_known"
POLL_INTERVAL = 300


async def _enabled(ctx):
    async with ctx.database.session() as s:
        r = await s.execute(select(BotFlag).where(BotFlag.key == _ENABLED_KEY))
        row = r.scalar_one_or_none()
        return row is not None and row.value == "1"


async def _set_enabled(ctx, value):
    async with ctx.database.session() as s:
        r = await s.execute(select(BotFlag).where(BotFlag.key == _ENABLED_KEY))
        row = r.scalar_one_or_none()
        v = "1" if value else "0"
        if row is None:
            s.add(BotFlag(key=_ENABLED_KEY, value=v))
        else:
            row.value = v


async def _known(ctx):
    async with ctx.database.session() as s:
        r = await s.execute(select(BotFlag).where(BotFlag.key == _KNOWN_KEY))
        row = r.scalar_one_or_none()
    if row is None:
        return set()
    try:
        return set(json.loads(row.value))
    except Exception:
        return set()


async def _save_known(ctx, hashes):
    val = json.dumps(sorted(hashes))
    async with ctx.database.session() as s:
        r = await s.execute(select(BotFlag).where(BotFlag.key == _KNOWN_KEY))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(BotFlag(key=_KNOWN_KEY, value=val))
        else:
            row.value = val


async def _fetch_authorizations(client):
    """Return the list of authorizations for the active account."""
    resp = await client(GetAuthorizationsRequest())
    return resp.authorizations


@command(r"sessionkiller(?: (on|off))?", "Turn session killer on/off",
         permission="sudo")
async def toggle(event):
    ctx = event.ctx
    arg = (event.pattern_match.group(1) or "").lower()
    if arg in ("on", "off"):
        await _set_enabled(ctx, arg == "on")
        if arg == "on":
            try:
                auths = await _fetch_authorizations(event.client)
                await _save_known(ctx, {a.hash for a in auths})
            except Exception:
                pass
    state = "🟢 ON" if await _enabled(ctx) else "🔴 OFF"
    await event.edit(Messages.info(f"Session killer: **{state}**"))


@command("authsessions", "List active sessions on this account", permission="sudo")
async def authsessions(event):
    try:
        auths = await _fetch_authorizations(event.client)
    except Exception as e:
        await event.edit(Messages.error(str(e)))
        return
    lines = [f"🔐 **Sessions ({len(auths)})**", SEP_FANCY]
    for a in auths:
        cur = " ⬅️ current" if getattr(a, "current", False) else ""
        created = datetime.fromtimestamp(a.date_created, tz=timezone.utc)
        lines.append(
            f"• {a.device_model or '?'} — {a.platform or '?'}{cur}\n"
            f"  `hash={a.hash[:12]}…` · {created:%Y-%m-%d} · `{a.ip}` ({a.country})")
    await event.edit("\n".join(lines))


async def _check(ctx):
    try:
        auths = await _fetch_authorizations(ctx.client)
    except Exception as e:
        logger.debug(f"{ctx.log_tag} GetAuthorizations: {e}")
        return
    known = await _known(ctx)
    me = await ctx.client.get_me()
    changed = False
    for a in auths:
        if getattr(a, "current", False):
            continue
        if a.hash in known:
            continue
        try:
            await ctx.client(ResetAuthorizationRequest(hash=a.hash))
            killed = True
        except Exception:
            killed = False
        text = (
            f"⚠️ **New session detected**\n{SEP_FANCY}\n"
            f"device: `{a.device_model or '?'}`\n"
            f"platform: `{a.platform or '?'}`\n"
            f"app: `{a.app_name} v{a.app_version}`\n"
            f"ip: `{a.ip}` ({a.country})\n"
            f"created: "
            f"`{datetime.fromtimestamp(a.date_created, tz=timezone.utc):%Y-%m-%d %H:%M}`\n\n"
            f"action: {'✅ killed' if killed else '❌ manual reset required'}")
        try:
            await ctx.client.send_message(me.id, text)
        except Exception:
            pass
        known.add(a.hash)
        changed = True
    if changed:
        await _save_known(ctx, known)


async def _poller(ctx):
    logger.info(f"{ctx.log_tag} sessionkiller poller started")
    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)
            if not await _enabled(ctx):
                continue
            await _check(ctx)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"{ctx.log_tag} poller: {e}", exc_info=True)


async def on_startup(ctx):
    return asyncio.create_task(_poller(ctx))
