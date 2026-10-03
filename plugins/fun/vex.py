"""Vex — spam, fake headers, troll transforms, snipe. Account-scoped."""
import asyncio
import html
import random
from collections import deque

from telethon import events

from core.decorators import command, listener
from core.module import ModuleMeta
from utils import Messages

META = ModuleMeta(
    name="vex", category="fun",
    description="Spam, fake headers, troll transforms, snipe.",
    permission="user",
)

_spam_active = {}
_SPAM_MAX = 100
_SPAM_DELAY = 0.35
_LEET = str.maketrans({
    "a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7", "b": "8", "g": "9",
    "A": "4", "E": "3", "I": "1", "O": "0", "S": "5", "T": "7", "B": "8", "G": "9",
})


def _esc(s):
    return html.escape(s or "")


@command(r"spam (\d+) (.+)", "Spam N times", permission="sudo")
async def spam(e):
    count = int(e.pattern_match.group(1))
    text = e.pattern_match.group(2)
    if count < 1 or count > _SPAM_MAX:
        await e.edit(Messages.error(f"Count 1–{_SPAM_MAX}."))
        return
    key = (e.ctx.account_id, e.sender_id)
    _spam_active[key] = True
    await e.delete()
    sent = 0
    try:
        for _ in range(count):
            if not _spam_active.get(key):
                break
            try:
                await e.client.send_message(e.chat_id, text)
                sent += 1
            except Exception:
                break
            await asyncio.sleep(_SPAM_DELAY)
    finally:
        _spam_active[key] = False
    note = await e.client.send_message(e.chat_id, f"✅ sent {sent}/{count}")
    await asyncio.sleep(4)
    try:
        await note.delete()
    except Exception:
        pass


@command("spamstop", "Stop your running spam", permission="sudo")
async def spamstop(e):
    _spam_active[(e.ctx.account_id, e.sender_id)] = False
    await e.edit(Messages.success("Spam stopped."))


@command(r"fakeme (.+)", "Fake your-name header")
async def fakeme(e):
    me = await e.client.get_me()
    display = f"{me.first_name or ''} {me.last_name or ''}".strip() or "Me"
    await e.edit(
        f"<b>{_esc(display)}</b>\n{_esc(e.pattern_match.group(1))}",
        parse_mode="html",
    )


@command(r"faketag (\S+) (.+)", "Fake @handle header")
async def faketag(e):
    h = e.pattern_match.group(1)
    if not h.startswith("@"):
        h = "@" + h
    await e.edit(
        f"<b>{_esc(h)}</b>\n{_esc(e.pattern_match.group(2))}",
        parse_mode="html",
    )


@command(r"reverse_ (.+)", "Reverse (alt)")
async def reverse_alt(e):
    await e.edit(e.pattern_match.group(1)[::-1])


@command(r"leet (.+)", "1337 sp34k")
async def leet(e):
    await e.edit(e.pattern_match.group(1).translate(_LEET))


def _uwu(text):
    for a, b in [("r", "w"), ("R", "W"), ("l", "w"), ("L", "W"),
                 ("th", "f"), ("TH", "F")]:
        text = text.replace(a, b)
    return f"{text} {random.choice(['uwu', 'owo', 'UwU', '>w<', '^w^'])}"


@command(r"uwu (.+)", "UwU-ify")
async def uwu(e):
    await e.edit(_uwu(e.pattern_match.group(1)))


@command(r"clap (.+)", "Clap between words")
async def clap(e):
    await e.edit(" 👏 ".join(e.pattern_match.group(1).split()) + " 👏")


_cache = {}
_sniped = {}


def _cache_deque(account_id, chat_id):
    return _cache.setdefault((account_id, chat_id), deque(maxlen=300))


def _sniped_deque(account_id, chat_id):
    return _sniped.setdefault((account_id, chat_id), deque(maxlen=10))


@listener(events.NewMessage())
async def cache_watcher(e):
    if not e.raw_text:
        return
    ctx = getattr(e.client, "ctx", None)
    if ctx is None:
        return
    sender = await e.get_sender()
    name = "—"
    if sender:
        name = (
            f"{getattr(sender, 'first_name', '') or ''} "
            f"{getattr(sender, 'last_name', '') or ''}"
        ).strip() or getattr(sender, "username", "") or str(e.sender_id)
    _cache_deque(ctx.account_id, e.chat_id).append(
        {"id": e.message.id, "sender_name": name, "text": e.raw_text}
    )


@listener(events.MessageDeleted())
async def delete_watcher(e):
    ctx = getattr(e.client, "ctx", None)
    if ctx is None or e.chat_id is None:
        return
    cache = _cache.get((ctx.account_id, e.chat_id))
    if not cache:
        return
    for mid in e.deleted_ids:
        for entry in list(cache):
            if entry["id"] == mid:
                _sniped_deque(ctx.account_id, e.chat_id).append(entry)
                try:
                    cache.remove(entry)
                except ValueError:
                    pass
                break


@command(r"snipe(?:\s+(\d+))?", "Show recently deleted message")
async def snipe(e):
    n = int(e.pattern_match.group(1) or 1)
    entries = list(_sniped_deque(e.ctx.account_id, e.chat_id))
    if not entries:
        await e.edit(Messages.info("Nothing to snipe."))
        return
    if n < 1 or n > len(entries):
        await e.edit(Messages.error(f"Only {len(entries)}."))
        return
    x = entries[-n]
    await e.edit(
        f"🔫 **Sniped**\n**Sender:** {x['sender_name'] or '—'}\n**Text:** {x['text']}"
    )


@command("vexhelp", "Vex help")
async def vexhelp(e):
    await e.edit(
        "🔥 **VEX**\n`.spam .spamstop .fakeme .faketag .leet .uwu .clap .snipe`"
    )
