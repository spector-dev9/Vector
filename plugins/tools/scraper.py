"""Scraper — enumerate group members, classify by activity, add to a target group.

State is stored per-account under data/accounts/<id>/files/scraper/<chat_id>.json
so no DB migration is needed.

⚠️ Adding unsolicited members to a group is against Telegram ToS.
   Use only on groups you own or have explicit permission to populate.
   Your account can be reported and banned. The module enforces delays and
   caps, but cannot make this safe.
"""
import asyncio
import json
import random
import time
from datetime import datetime, timezone

from telethon import functions
from telethon.errors import (
    FloodWaitError, PeerFloodError,
    UserPrivacyRestrictedError, UserNotMutualContactError,
    UserChannelsTooMuchError, UserAlreadyParticipantError,
    UserKickedError, InputUserDeactivatedError,
    ChatAdminRequiredError,
)

from core.decorators import command
from core.logger import setup_logger
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY, Formatters

META = ModuleMeta(
    name="scraper", category="tools",
    description="Scrape members, classify by activity, add to a target group.",
    permission="sudo",
)

logger = setup_logger("VECTOR.scraper")

# ── safety caps ──────────────────────────────────────────────
MAX_SCRAPE = 5000            # max members to enumerate per run
MAX_ADD_PER_RUN = 50         # hard cap on adds per command invocation
MIN_ADD_DELAY = 8.0          # seconds between adds (jittered up to MAX)
MAX_ADD_DELAY = 15.0
TARGET_COOLDOWN_HOURS = 24   # same target can't be added to twice in 24h
ACTIVITY_LOOKBACK = 1000     # scan this many recent messages for activity
ACTIVE_MIN_MSGS = 3          # >= this many msgs → active
INACTIVE_MAX_MSGS = 0        # == this many msgs → inactive

_STATE = {}


def _state(ctx):
    return _STATE.setdefault(ctx.account_id, {
        "adding": False,
        "stop": False,
        "cooldowns": {},   # target_chat_id -> unix ts of last add
    })


# ─────────────────────────────────────────────────────────────
#  scrape file I/O
# ─────────────────────────────────────────────────────────────

def _file(ctx, chat_id: int):
    return ctx.paths.sub("scraper") / f"{chat_id}.json"


def _save(ctx, chat_id: int, data: dict):
    try:
        _file(ctx, chat_id).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"scrape save failed for {chat_id}: {e}")


def _load(ctx, chat_id: int):
    p = _file(ctx, chat_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
#  scrape
# ─────────────────────────────────────────────────────────────

@command(r"scrape(?:\s+(\S+))?", "Enumerate members of a chat and save to disk",
         permission="sudo")
async def scrape(event):
    """
    Enumerate members of the target chat and store them.

        .scrape                → use current chat
        .scrape @somegroup     → resolve by username
        .scrape -1001234567890 → by id
    """
    ctx = event.ctx
    raw = (event.pattern_match.group(1) or "").strip()

    await event.edit(Messages.loading("Resolving chat…"))
    try:
        if raw:
            entity = await event.client.get_entity(raw)
        else:
            entity = await event.get_chat()
    except Exception as e:
        await event.edit(Messages.error(f"Resolve failed: {e}"))
        return

    title = getattr(entity, "title", None) or "chat"
    await event.edit(Messages.loading(
        f"Enumerating members of **{title}**…\n_This can take a minute._"
    ))

    members = []
    try:
        async for u in event.client.iter_participants(entity, aggressive=False):
            if len(members) >= MAX_SCRAPE:
                break
            try:
                members.append({
                    "id": u.id,
                    "username": getattr(u, "username", None),
                    "first_name": getattr(u, "first_name", "") or "",
                    "last_name": getattr(u, "last_name", "") or "",
                    "bot": bool(getattr(u, "bot", False)),
                    "deleted": bool(getattr(u, "deleted", False)),
                    "premium": bool(getattr(u, "premium", False)),
                })
            except Exception:
                continue
    except Exception as e:
        await event.edit(Messages.error(f"Enumeration failed: {e}"))
        return

    data = {
        "chat_id": entity.id,
        "title": title,
        "scraped_at": time.time(),
        "total": len(members),
        "members": members,
        "activity": {},     # populated by .scrapeactivity
        "classes": {},      # active / inactive / unknown
    }
    _save(ctx, entity.id, data)

    bots = sum(1 for m in members if m["bot"])
    deleted = sum(1 for m in members if m["deleted"])
    await event.edit(Messages.success(
        f"Scraped **{len(members)}** member(s) from **{title}**.\n"
        f"• bots: **{bots}**\n"
        f"• deleted: **{deleted}**\n"
        f"• real users: **{len(members) - bots - deleted}**\n"
        f"\n_Saved. Next: `.scrapeactivity` to classify._"
    ))


# ─────────────────────────────────────────────────────────────
#  activity classification
# ─────────────────────────────────────────────────────────────

@command(r"scrapeactivity(?:\s+(\d+))?", "Classify scraped members by activity",
         permission="sudo")
async def scrapeactivity(event):
    """
    Scan the last N messages in the chat and count per sender.

        .scrapeactivity          → scan 1000 messages (default)
        .scrapeactivity 3000     → scan more
    """
    ctx = event.ctx
    n = int(event.pattern_match.group(1) or ACTIVITY_LOOKBACK)
    n = max(100, min(n, 10000))

    chat = await event.get_chat()
    data = _load(ctx, chat.id)
    if data is None:
        await event.edit(Messages.error(
            "No scraped members for this chat.\n_Use `.scrape` first._"))
        return

    await event.edit(Messages.loading(
        f"Scanning last **{n}** messages for activity…"
    ))

    counts: dict[int, int] = {}
    scanned = 0
    try:
        async for m in event.client.iter_messages(chat, limit=n):
            scanned += 1
            sid = getattr(m, "sender_id", None)
            if sid is None:
                continue
            counts[sid] = counts.get(sid, 0) + 1
            if scanned % 500 == 0:
                try:
                    await event.edit(
                        f"⏳ Scanned **{scanned}/{n}** · "
                        f"**{len(counts)}** unique senders…")
                except Exception:
                    pass
    except Exception as e:
        await event.edit(Messages.error(f"Scan failed: {e}"))
        return

    active, inactive, unknown = [], [], []
    for m in data["members"]:
        if m["bot"] or m["deleted"]:
            continue
        c = counts.get(m["id"], 0)
        if c >= ACTIVE_MIN_MSGS:
            m["msg_count"] = c
            active.append(m["id"])
        elif c == INACTIVE_MAX_MSGS:
            m["msg_count"] = 0
            inactive.append(m["id"])
        else:
            m["msg_count"] = c
            unknown.append(m["id"])

    data["activity"] = {str(k): v for k, v in counts.items()}
    data["classes"] = {
        "active": active,
        "inactive": inactive,
        "unknown": unknown,
        "scanned_msgs": scanned,
    }
    _save(ctx, chat.id, data)

    await event.edit(Messages.success(
        f"Classified **{len(data['members'])}** members.\n"
        f"{SEP_FANCY}\n"
        f"🟢 active: **{len(active)}** (≥{ACTIVE_MIN_MSGS} msgs)\n"
        f"🔴 inactive: **{len(inactive)}** (0 msgs in last {scanned})\n"
        f"⚪ unknown: **{len(unknown)}** (1–{ACTIVE_MIN_MSGS-1} msgs)\n"
        f"{SEP_FANCY}\n"
        f"_Next:_ `.addactive <target>` or `.addinactive <target>`"
    ))


@command("scrapestats", "Show scrape summary for this chat", permission="sudo")
async def scrapestats(event):
    ctx = event.ctx
    chat = await event.get_chat()
    data = _load(ctx, chat.id)
    if data is None:
        await event.edit(Messages.info("No scrape for this chat."))
        return
    cls = data.get("classes", {})
    when = datetime.fromtimestamp(data["scraped_at"], tz=timezone.utc)
    await event.edit(
        f"📊 **Scrape — {data.get('title', '?')}**\n{SEP_FANCY}\n"
        f"**Total members**  `{data['total']}`\n"
        f"**Scraped at**     `{when:%Y-%m-%d %H:%M}` UTC\n"
        f"{SEP_FANCY}\n"
        f"🟢 active      `{len(cls.get('active', []))}`\n"
        f"🔴 inactive    `{len(cls.get('inactive', []))}`\n"
        f"⚪ unknown     `{len(cls.get('unknown', []))}`\n"
        f"📩 scanned msgs `{cls.get('scanned_msgs', 0)}`\n"
        f"{SEP_FANCY}\n"
        f"_Use `.scrapelist` to see the actual IDs._"
    )


@command(r"scrapelist(?:\s+(active|inactive|unknown))?(?:\s+(\d+))?",
         "List scraped members by class", permission="sudo")
async def scrapelist(event):
    ctx = event.ctx
    chat = await event.get_chat()
    data = _load(ctx, chat.id)
    if data is None:
        await event.edit(Messages.info("No scrape for this chat."))
        return
    cls = data.get("classes", {})
    if not cls:
        await event.edit(Messages.info("Run `.scrapeactivity` first."))
        return

    which = (event.pattern_match.group(1) or "active").lower()
    limit = int(event.pattern_match.group(2) or 30)
    ids = cls.get(which, [])
    if not ids:
        await event.edit(Messages.info(f"No {which} members."))
        return

    by_id = {m["id"]: m for m in data["members"]}
    lines = [f"📋 **{which.upper()}** · {len(ids)} total", SEP_FANCY]
    for uid in ids[:limit]:
        m = by_id.get(uid)
        if not m:
            continue
        handle = f"@{m['username']}" if m["username"] else "—"
        name = f"{m['first_name']} {m['last_name']}".strip() or "—"
        cnt = m.get("msg_count", 0)
        lines.append(f"`{uid}` · {name[:25]} · {handle} · {cnt}m")
    if len(ids) > limit:
        lines.append(f"_…+{len(ids)-limit} more_")
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n_…truncated_"
    await event.edit(text)


# ─────────────────────────────────────────────────────────────
#  add to target group
# ─────────────────────────────────────────────────────────────

def _cooldown_left(st, target_id):
    last = st["cooldowns"].get(target_id, 0)
    if not last:
        return 0
    left = (last + TARGET_COOLDOWN_HOURS * 3600) - time.time()
    return max(0, int(left))


async def _do_add(event, target_arg, which, limit):
    ctx = event.ctx
    st = _state(ctx)

    if st["adding"]:
        await event.edit(Messages.warning(
            "An add operation is already running.\n_Use `.stopadd` to abort._"))
        return

    # source
    src = await event.get_chat()
    data = _load(ctx, src.id)
    if data is None or not data.get("classes"):
        await event.edit(Messages.error(
            "No classified members. Run `.scrape` then `.scrapeactivity`."))
        return

    ids = data["classes"].get(which, [])
    if not ids:
        await event.edit(Messages.info(f"No {which} members."))
        return

    # target
    try:
        target = await event.client.get_entity(target_arg)
    except Exception as e:
        await event.edit(Messages.error(f"Target resolve failed: {e}"))
        return

    target_id = target.id
    left = _cooldown_left(st, target_id)
    if left > 0:
        h = left // 3600
        m = (left % 3600) // 60
        await event.edit(Messages.warning(
            f"Target on cooldown · {h}h {m}m remaining."))
        return

    # target must be a group we can invite to
    if not hasattr(target, "title"):
        await event.edit(Messages.error("Target must be a group or channel."))
        return

    n = min(limit, len(ids), MAX_ADD_PER_RUN)
    await event.edit(
        f"🚀 **Adding {n} {which} member(s)** → **{getattr(target, 'title', '?')}**\n"
        f"{SEP_FANCY}\n"
        f"_Delay: {MIN_ADD_DELAY:.0f}–{MAX_ADD_DELAY:.0f}s between adds_\n"
        f"_Use `.stopadd` to abort._"
    )

    st["adding"] = True
    st["stop"] = False

    # fetch source entities for the members we're about to add
    by_id = {m["id"]: m for m in data["members"]}
    added = failed = skipped = 0
    start = time.time()

    try:
        for i, uid in enumerate(ids[:n], 1):
            if st["stop"]:
                break

            # skip bots / deleted
            info = by_id.get(uid)
            if info and (info["bot"] or info["deleted"]):
                skipped += 1
                continue

            # resolve user entity
            try:
                user = await event.client.get_entity(uid)
            except Exception:
                skipped += 1
                continue

            try:
                if hasattr(target, "broadcast") or target.__class__.__name__ == "Channel":
                    await event.client(functions.channels.InviteToChannelRequest(
                        channel=target, users=[user],
                    ))
                else:
                    await event.client(functions.messages.AddChatUserRequest(
                        chat_id=target.id, user_id=user, fwd_limit=50,
                    ))
                added += 1
            except FloodWaitError as e:
                wait = int(e.seconds) + 5
                logger.warning(f"floodwait {wait}s")
                try:
                    await event.edit(
                        f"⏸ FloodWait **{wait}s**\n"
                        f"Added: **{added}** · failed: **{failed}**")
                except Exception:
                    pass
                await asyncio.sleep(wait)
                # retry once
                try:
                    if hasattr(target, "broadcast"):
                        await event.client(functions.channels.InviteToChannelRequest(
                            channel=target, users=[user],
                        ))
                    else:
                        await event.client(functions.messages.AddChatUserRequest(
                            chat_id=target.id, user_id=user, fwd_limit=50,
                        ))
                    added += 1
                except Exception:
                    failed += 1
            except PeerFloodError:
                await event.edit(Messages.error(
                    f"⛔ PeerFlood — Telegram is limiting adds.\n"
                    f"Added **{added}** so far. Stop now."))
                break
            except (
                UserPrivacyRestrictedError,
                UserNotMutualContactError,
                UserChannelsTooMuchError,
                UserKickedError,
                InputUserDeactivatedError,
                UserAlreadyParticipantError,
            ):
                skipped += 1
            except ChatAdminRequiredError:
                await event.edit(Messages.error(
                    "⛔ You need invite permission in the target group."))
                break
            except Exception as e:
                logger.warning(f"add {uid}: {type(e).__name__}: {e}")
                failed += 1

            # progress
            if i % 5 == 0 or i == n:
                try:
                    await event.edit(
                        f"🚀 **{i}/{n}** · added **{added}** · "
                        f"failed **{failed}** · skipped **{skipped}**"
                    )
                except Exception:
                    pass

            # jitter delay
            await asyncio.sleep(random.uniform(MIN_ADD_DELAY, MAX_ADD_DELAY))

    finally:
        st["adding"] = False
        st["stop"] = False
        st["cooldowns"][target_id] = time.time()

    elapsed = int(time.time() - start)
    await event.edit(Messages.success(
        f"**Add complete** → **{getattr(target, 'title', '?')}**\n"
        f"{SEP_FANCY}\n"
        f"✅ added      `{added}`\n"
        f"❌ failed     `{failed}`\n"
        f"⏭️ skipped    `{skipped}`\n"
        f"⏱ elapsed    `{elapsed}s`\n"
        f"{SEP_FANCY}\n"
        f"_Target on {TARGET_COOLDOWN_HOURS}h cooldown._"
    ))


@command(r"addactive (\S+)(?:\s+(\d+))?", "Add active members to a target group",
         permission="sudo")
async def addactive(event):
    """Usage: `.addactive @targetgroup [count]`"""
    target = event.pattern_match.group(1)
    limit = int(event.pattern_match.group(2) or 30)
    await _do_add(event, target, "active", limit)


@command(r"addinactive (\S+)(?:\s+(\d+))?", "Add inactive members to a target group",
         permission="sudo")
async def addinactive(event):
    """Usage: `.addinactive @targetgroup [count]`"""
    target = event.pattern_match.group(1)
    limit = int(event.pattern_match.group(2) or 30)
    await _do_add(event, target, "inactive", limit)


@command("stopadd", "Abort the running add operation", permission="sudo")
async def stopadd(event):
    ctx = event.ctx
    st = _state(ctx)
    if not st["adding"]:
        await event.edit(Messages.info("No add operation running."))
        return
    st["stop"] = True
    await event.edit(Messages.success("Stop requested. Finishing current add…"))


# ─────────────────────────────────────────────────────────────
#  help
# ─────────────────────────────────────────────────────────────

@command("scraperhelp", "Scraper help")
async def scraperhelp(event):
    await event.edit(
        "🕸 **SCRAPER**\n"
        f"{SEP_FANCY}\n\n"
        "**Scrape:**\n"
        "▸ `.scrape` — current chat\n"
        "▸ `.scrape @group` — resolve by username\n\n"
        "**Classify:**\n"
        "▸ `.scrapeactivity [n]` — scan last N msgs\n"
        "▸ `.scrapestats` — summary\n"
        "▸ `.scrapelist [active|inactive|unknown] [n]`\n\n"
        "**Add to target:**\n"
        "▸ `.addactive @target [count]`\n"
        "▸ `.addinactive @target [count]`\n"
        "▸ `.stopadd` — abort\n\n"
        f"{SEP_FANCY}\n"
        f"**Caps:**\n"
        f"• max {MAX_SCRAPE} members per scrape\n"
        f"• max {MAX_ADD_PER_RUN} adds per run\n"
        f"• {MIN_ADD_DELAY:.0f}–{MAX_ADD_DELAY:.0f}s jittered delay\n"
        f"• {TARGET_COOLDOWN_HOURS}h cooldown per target\n"
        f"• active ≥ {ACTIVE_MIN_MSGS} msgs · inactive = 0 msgs\n\n"
        "⚠️ _Adding unsolicited members is against Telegram ToS. "
        "Only use on groups you own. PeerFlood aborts the run._"
    )