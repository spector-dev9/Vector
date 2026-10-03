"""Send test view-once / self-destruct media."""
import io
import random
import httpx
from core.decorators import command
from core.module import ModuleMeta
from utils import Messages

META = ModuleMeta(
    name="sendonce", category="media",
    description="Send view-once / self-destruct test media.",
    permission="user",
)

VIEW_ONCE = 2147483647
_TIMERS = {"5": 5, "10": 10, "30": 30, "60": 60, "1m": 60, "2m": 120,
           "5s": 5, "10s": 10, "30s": 30, "60s": 60, "5m": 300}


async def _fetch(kw):
    seed = random.randint(1, 999999)
    url = (f"https://loremflickr.com/720/720/{kw}?random={seed}" if kw
           else f"https://picsum.photos/720/720?random={seed}")
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            buf = io.BytesIO(r.content)
            buf.name = f"once_{seed}.jpg"
            return buf
    except Exception:
        return None


def _parse(raw):
    if not raw:
        return VIEW_ONCE, None
    parts = raw.strip().split(None, 1)
    first = parts[0].lower()
    if first in ("view", "once"):
        return VIEW_ONCE, (parts[1].strip() if len(parts) > 1 else None)
    if first in _TIMERS:
        return _TIMERS[first], (parts[1].strip() if len(parts) > 1 else None)
    return VIEW_ONCE, raw.strip()


@command(r"once(?: (.+))?", "Send view-once / self-destruct media")
async def once(event):
    ttl, kw = _parse(event.pattern_match.group(1))
    label = "view-once" if ttl == VIEW_ONCE else f"self-destruct {ttl}s"
    await event.edit(Messages.loading(f"Preparing {label}…"))
    buf = await _fetch(kw)
    if not buf:
        await event.edit(Messages.error("Fetch failed."))
        return
    try:
        await event.client.send_file(
            event.chat_id, buf,
            caption=f"🧪 **{label}**\nTag: {kw or 'random'}",
            ttl=ttl,
        )
        await event.delete()
    except Exception as e:
        await event.edit(Messages.error(str(e)))
