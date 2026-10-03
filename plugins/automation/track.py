"""Track — observe activity events."""
from datetime import datetime, timezone

from sqlalchemy import select
from telethon import events
from telethon.tl.types import UserStatusOnline, UserStatusOffline

from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import TrackedUser, ActivitySession
from helpers.telegram.messages import resolve_target
from helpers.telegram.users import warm_user_cache
from utils import Messages, SEP_FANCY, Formatters

META = ModuleMeta(
    name="track", category="automation",
    description="Observe supported activity events for a user.",
    permission="user",
)

MIN_SESSION_SECONDS = 45


async def _is_tracked(ctx, uid):
    async with ctx.database.session() as s:
        r = await s.execute(
            select(TrackedUser).where(
                TrackedUser.user_id == uid, TrackedUser.enabled == 1,
            )
        )
        return r.scalar_one_or_none() is not None


async def _open_session(ctx, uid):
    async with ctx.database.session() as s:
        r = await s.execute(
            select(ActivitySession).where(
                ActivitySession.user_id == uid,
                ActivitySession.ended_at.is_(None),
            )
        )
        if r.scalar_one_or_none() is not None:
            return False
        s.add(ActivitySession(
            user_id=uid, chat_id=None,
            started_at=datetime.now(timezone.utc),
            ended_at=None, duration=0,
        ))
        return True


async def _close_session(ctx, uid):
    async with ctx.database.session() as s:
        r = await s.execute(
            select(ActivitySession)
            .where(
                ActivitySession.user_id == uid,
                ActivitySession.ended_at.is_(None),
            )
            .order_by(ActivitySession.started_at.desc())
            .limit(1)
        )
        row = r.scalar_one_or_none()
        if row is None:
            return 0
        now = datetime.now(timezone.utc)
        started = row.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        dur = int((now - started).total_seconds())
        if dur < MIN_SESSION_SECONDS:
            await s.delete(row)
            return 0
        row.ended_at = now
        row.duration = dur
        return dur


@listener(events.UserUpdate())
async def _watcher(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None:
        return
    uid = getattr(event, "user_id", None)
    if uid is None:
        return
    if not await _is_tracked(ctx, uid):
        return
    status = getattr(event, "status", None)
    if isinstance(status, UserStatusOnline):
        await _open_session(ctx, uid)
    elif isinstance(status, UserStatusOffline):
        await _close_session(ctx, uid)


@command(r"track(?:\s+(.+))?", "Start tracking a user")
async def track_handler(event):
    ctx = event.ctx
    target = await resolve_target(event.client, event, event.pattern_match.group(1))
    if target is None:
        await event.edit(Messages.error("Couldn't resolve user."))
        return
    await warm_user_cache(event.client, target.id)
    async with ctx.database.session() as s:
        r = await s.execute(select(TrackedUser).where(TrackedUser.user_id == target.id))
        row = r.scalar_one_or_none()
        if row is None:
            s.add(TrackedUser(user_id=target.id, enabled=1))
            action = "started"
        else:
            row.enabled = 1
            action = "resumed"
    name = f"{target.first_name or ''} {target.last_name or ''}".strip() or str(target.id)
    await event.edit(Messages.success(
        f"📍 Now tracking **{name}**\n_({action}) · flicker filter: {MIN_SESSION_SECONDS}s_"
    ))


@command(r"untrack(?:\s+(.+))?", "Stop tracking a user")
async def untrack_handler(event):
    ctx = event.ctx
    target = await resolve_target(event.client, event, event.pattern_match.group(1))
    if target is None:
        await event.edit(Messages.error("Couldn't resolve user."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(TrackedUser).where(TrackedUser.user_id == target.id))
        row = r.scalar_one_or_none()
        if row is None or row.enabled == 0:
            await event.edit(Messages.warning("Not tracked."))
            return
        row.enabled = 0
    await _close_session(ctx, target.id)
    await event.edit(Messages.success(f"Stopped tracking `{target.id}`."))


@command("tracked", "List tracked users")
async def tracked_handler(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(select(TrackedUser).order_by(TrackedUser.created_at.desc()))
        rows = r.scalars().all()
    if not rows:
        await event.edit(Messages.info("No tracked users."))
        return
    lines = ["📍 **TRACKED USERS**", SEP_FANCY, ""]
    for t in rows:
        async with ctx.database.session() as s:
            r = await s.execute(
                select(ActivitySession).where(
                    ActivitySession.user_id == t.user_id,
                    ActivitySession.ended_at.is_not(None),
                    ActivitySession.duration > 0,
                )
            )
            sess = r.scalars().all()
        total = sum(x.duration for x in sess)
        mark = "🟢" if t.enabled else "⚪"
        lines.append(
            f"{mark} `{t.user_id}` — sessions: {len(sess)} · total: "
            f"{Formatters.format_duration(total) if total else '—'}"
        )
    await event.edit("\n".join(lines))


@command(r"sessions(?:\s+(.+))?", "Show sessions for a user")
async def sessions_handler(event):
    ctx = event.ctx
    target = await resolve_target(event.client, event, event.pattern_match.group(1))
    if target is None:
        await event.edit(Messages.error("Couldn't resolve user."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(
            select(ActivitySession)
            .where(ActivitySession.user_id == target.id)
            .order_by(ActivitySession.started_at.desc())
            .limit(50)
        )
        rows = r.scalars().all()
    real = [x for x in rows if x.ended_at and x.duration >= MIN_SESSION_SECONDS]
    if not real:
        await event.edit(Messages.info("No sessions recorded yet."))
        return
    total = sum(x.duration for x in real)
    lines = [
        f"📊 **SESSIONS — {target.first_name or target.id}**",
        SEP_FANCY,
        f"sessions: **{len(real)}**",
        f"total:    **{Formatters.format_duration(total)}**",
        SEP_FANCY,
    ]
    for r in real[:10]:
        lines.append(
            f"  {r.started_at:%d %b %H:%M} → {Formatters.format_duration(r.duration)}"
        )
    await event.edit("\n".join(lines))


@command(r"trackclear(?:\s+(.+))?", "Clear sessions for a user")
async def trackclear_handler(event):
    ctx = event.ctx
    target = await resolve_target(event.client, event, event.pattern_match.group(1))
    if target is None:
        await event.edit(Messages.error("Couldn't resolve."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(ActivitySession).where(
            ActivitySession.user_id == target.id))
        rows = r.scalars().all()
        n = len(rows)
        for row in rows:
            await s.delete(row)
    await event.edit(Messages.success(f"Cleared **{n}** session(s)."))


@command(r"trackdel(?:\s+(.+))?", "Fully remove a tracked user", permission="sudo")
async def trackdel_handler(event):
    ctx = event.ctx
    target = await resolve_target(event.client, event, event.pattern_match.group(1))
    if target is None:
        await event.edit(Messages.error("Couldn't resolve."))
        return
    async with ctx.database.session() as s:
        r = await s.execute(select(ActivitySession).where(
            ActivitySession.user_id == target.id))
        sessions = r.scalars().all()
        for row in sessions:
            await s.delete(row)
        r = await s.execute(select(TrackedUser).where(TrackedUser.user_id == target.id))
        tracked = r.scalars().all()
        for row in tracked:
            await s.delete(row)
    await event.edit(Messages.success(
        f"Removed `{target.id}` completely.\n"
        f"sessions: **{len(sessions)}** · tracked rows: **{len(tracked)}**"
    ))


async def on_startup(ctx):
    async with ctx.database.session() as s:
        r = await s.execute(select(ActivitySession).where(
            ActivitySession.ended_at.is_(None)))
        rows = r.scalars().all()
        for row in rows:
            row.ended_at = row.started_at
            row.duration = 0
