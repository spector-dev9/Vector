"""Schedule — sends at specific time via runner task."""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select

from core.decorators import command
from core.logger import setup_logger
from core.module import ModuleMeta
from database.models import Schedule
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="schedule", category="automation",
    description="Schedule messages once, or recurring on a weekday.",
    permission="user",
)

logger = setup_logger("VECTOR.schedule")
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
RUNNER_INTERVAL = 30


def _parse_once(daytime):
    return datetime.strptime(daytime.strip(), "%Y-%m-%d %H:%M")


def _parse_week(daytime):
    parts = daytime.strip().split()
    if len(parts) != 2 or parts[0].lower() not in _DAYS:
        raise ValueError("format: <weekday> HH:MM")
    day = parts[0].lower()
    hhmm = datetime.strptime(parts[1], "%H:%M").time()
    target_idx = _DAYS.index(day)
    now = datetime.now()
    delta = (target_idx - now.weekday()) % 7
    run = (now + timedelta(days=delta)).replace(
        hour=hhmm.hour, minute=hhmm.minute, second=0, microsecond=0)
    if run <= now:
        run += timedelta(days=7)
    return run, day


async def _store(ctx, event, run, day_of_week):
    reply = await event.get_reply_message()
    if reply is None:
        await event.edit(Messages.error("Reply to a message to schedule it."))
        return
    try:
        fwd = await reply.forward_to("me")
    except Exception as e:
        await event.edit(Messages.error(f"Could not stash message: {e}"))
        return
    async with ctx.database.session() as s:
        s.add(Schedule(
            owner_id=event.sender_id,
            chat_id=event.chat_id,
            msg_id=reply.id,
            botlog_chat=0,
            botlog_msg=fwd.id,
            run_at=run,
            day_of_week=day_of_week,
        ))
    await event.edit(Messages.success(
        f"Scheduled for `{run:%Y-%m-%d %H:%M}`"
        + (f" every **{day_of_week}**" if day_of_week else "")
    ))


@command(r"schedule\s+([\s\S]+)", "Schedule a message once")
async def schedule_once(event):
    try:
        run = _parse_once(event.pattern_match.group(1))
    except Exception:
        await event.edit(Messages.error("Usage: `.schedule YYYY-MM-DD HH:MM` (reply)"))
        return
    if run <= datetime.now():
        await event.edit(Messages.error("That time is in the past."))
        return
    await _store(event.ctx, event, run, None)


@command(r"autoschedule\s+([\s\S]+)", "Schedule weekly repeating message")
async def schedule_week(event):
    try:
        run, day = _parse_week(event.pattern_match.group(1))
    except Exception as e:
        await event.edit(Messages.error(f"Usage: `.autoschedule <weekday> HH:MM` — {e}"))
        return
    await _store(event.ctx, event, run, day)


@command("myschedule", "Show your scheduled messages")
async def list_schedules(event):
    ctx = event.ctx
    async with ctx.database.session() as s:
        r = await s.execute(
            select(Schedule).where(Schedule.owner_id == event.sender_id)
            .order_by(Schedule.run_at)
        )
        rows = r.scalars().all()
    if not rows:
        await event.edit(Messages.info("No scheduled messages."))
        return
    lines = [f"📅 **Scheduled ({len(rows)})**", SEP_FANCY]
    for row in rows:
        tag = f" every {row.day_of_week}" if row.day_of_week else ""
        lines.append(f"• `#{row.id}` → `{row.run_at:%Y-%m-%d %H:%M}`{tag}")
    lines.append("\n_Delete with `.delschedule <id>`._")
    await event.edit("\n".join(lines))


@command(r"delschedule\s+(\d+)", "Delete a scheduled message")
async def del_schedule(event):
    ctx = event.ctx
    sid = int(event.pattern_match.group(1))
    async with ctx.database.session() as s:
        r = await s.execute(select(Schedule).where(
            Schedule.id == sid, Schedule.owner_id == event.sender_id))
        row = r.scalar_one_or_none()
        if row is None:
            await event.edit(Messages.error("Not found."))
            return
        await s.delete(row)
    await event.edit(Messages.success(f"Deleted #{sid}."))


async def _runner(ctx):
    logger.info(f"{ctx.log_tag} schedule runner started")
    while True:
        try:
            await asyncio.sleep(RUNNER_INTERVAL)
            now = datetime.now()
            async with ctx.database.session() as s:
                r = await s.execute(select(Schedule).where(Schedule.run_at <= now))
                due = r.scalars().all()
                for row in due:
                    try:
                        msg = await ctx.client.get_messages("me", ids=row.botlog_msg)
                        if msg:
                            await ctx.client.send_message(row.chat_id, msg)
                            logger.info(f"{ctx.log_tag} sent scheduled #{row.id}")
                    except Exception as e:
                        logger.warning(f"{ctx.log_tag} schedule #{row.id} send: {e}")
                    if row.day_of_week:
                        try:
                            run, _ = _parse_week(f"{row.day_of_week} {row.run_at:%H:%M}")
                            row.run_at = run
                        except Exception:
                            await s.delete(row)
                    else:
                        await s.delete(row)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"{ctx.log_tag} schedule runner: {e}", exc_info=True)


async def on_startup(ctx):
    return asyncio.create_task(_runner(ctx))
