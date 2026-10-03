"""Ping / alive."""
import asyncio
import os
import platform
import sys
import time

from core.decorators import command
from core.module import ModuleMeta
from helpers.network.http import fetch_text
from utils import Messages, SEP_FANCY, Formatters

try:
    import psutil
except ImportError:
    psutil = None

META = ModuleMeta(
    name="ping", category="tools",
    description="Latency, liveness and host snapshot.",
    permission="user",
)


# ─────────────────────────────────────────────────────────────
#  safe psutil wrappers — Termux/Android blocks /proc/stat
# ─────────────────────────────────────────────────────────────

def _cpu_percent() -> str:
    if psutil is None:
        return "—"
    try:
        return f"{psutil.cpu_percent(interval=0.3):.1f}%"
    except Exception:
        return "N/A"


def _ram() -> str:
    if psutil is None:
        return "—"
    try:
        m = psutil.virtual_memory()
        return (f"{m.percent:.0f}% · "
                f"{Formatters.format_size(m.used)}/"
                f"{Formatters.format_size(m.total)}")
    except Exception:
        return "N/A"


def _disk() -> str:
    if psutil is None:
        return "—"
    for path in (".", os.path.expanduser("~"), "/"):
        try:
            d = psutil.disk_usage(path)
            return (f"{d.percent:.0f}% · "
                    f"{Formatters.format_size(d.used)}/"
                    f"{Formatters.format_size(d.total)}")
        except Exception:
            continue
    return "N/A"


def _load_avg() -> str:
    if psutil is None:
        return "—"
    try:
        a, b, c = psutil.getloadavg()
        return f"{a:.2f} {b:.2f} {c:.2f}"
    except Exception:
        return "N/A"


def _boot_time() -> str:
    if psutil is None:
        return "—"
    try:
        secs = int(time.time() - psutil.boot_time())
        return Formatters.format_duration(secs)
    except Exception:
        return "N/A"


# ─────────────────────────────────────────────────────────────
#  latency probes
# ─────────────────────────────────────────────────────────────

async def _tg(client):
    t0 = time.perf_counter()
    await client.get_me()
    return (time.perf_counter() - t0) * 1000


async def _net():
    t0 = time.perf_counter()
    txt = await fetch_text("https://cloudflare.com/cdn-cgi/trace")
    return None if txt is None else (time.perf_counter() - t0) * 1000


def _rate(ms):
    for limit, dot, label in ((80, "🟢", "Excellent"), (150, "🟢", "Great"),
                              (300, "🟡", "Good"), (600, "🟠", "Fair"),
                              (1200, "🔴", "Slow")):
        if ms <= limit:
            return dot, label
    return "🔴", "Very slow"


# ─────────────────────────────────────────────────────────────
#  commands
# ─────────────────────────────────────────────────────────────

@command("ping", "Measure network latency")
async def ping(event):
    samples = []
    for _ in range(3):
        try:
            samples.append(await _tg(event.client))
        except Exception:
            pass
        await asyncio.sleep(0.08)
    if not samples:
        await event.edit(Messages.error("Unreachable."))
        return
    samples.sort()
    med = samples[len(samples) // 2]
    dot, rating = _rate(med)
    net = await _net()
    tail = f"\n**Internet**   `{net:>6.1f} ms`" if net else ""
    await event.edit(
        f"{dot} **PONG**\n{SEP_FANCY}\n"
        f"**Telegram**   `{med:>6.1f} ms` · {rating}\n"
        f"**Best**       `{samples[0]:>6.1f} ms`\n"
        f"**Worst**      `{samples[-1]:>6.1f} ms`{tail}")


@command("p", "Quick network ping")
async def p(event):
    try:
        ms = await _tg(event.client)
    except Exception:
        await event.edit(Messages.error("Unreachable."))
        return
    dot, rating = _rate(ms)
    await event.edit(f"{dot} `{ms:.0f} ms` · {rating}")


@command("alive", "Liveness + system status")
async def alive(event):
    ctx = event.ctx
    me = await event.client.get_me()
    st = ctx.state.get_stats()
    reg = ctx.registry.get_stats()
    up = Formatters.format_uptime(ctx.state.started_at)
    await event.edit(
        f"💎 **VECTOR ALIVE**\n{SEP_FANCY}\n"
        f"**Account**  `{ctx.account_id}`\n"
        f"**Handle**   @{me.username or '—'}\n"
        f"**Uptime**   {up}\n"
        f"**Commands** {st['commands']}\n"
        f"**Errors**   {st['errors']}\n"
        f"{SEP_FANCY}\n"
        f"🧠 CPU   {_cpu_percent()}\n"
        f"💾 RAM   {_ram()}\n"
        f"📀 Disk  {_disk()}\n"
        f"📊 Load  {_load_avg()}\n"
        f"⏱ Boot   {_boot_time()}\n"
        f"{SEP_FANCY}\n"
        f"📦 Modules  {reg['total_modules']}\n"
        f"🎁 Handlers {reg['total_handlers']}\n"
        f"🐍 Python   {sys.version.split()[0]}\n"
        f"🖥  Platform {platform.platform()[:40]}")


@command("sysinfo", "Detailed host info (Termux-safe)")
async def sysinfo(event):
    await event.edit(
        f"🖥 **HOST INFO**\n{SEP_FANCY}\n"
        f"**Python**    `{sys.version.split()[0]}`\n"
        f"**Platform**  `{platform.platform()[:50]}`\n"
        f"**Machine**   `{platform.machine()}`\n"
        f"**Processor** `{platform.processor() or '—'}`\n"
        f"{SEP_FANCY}\n"
        f"🧠 CPU   {_cpu_percent()}\n"
        f"💾 RAM   {_ram()}\n"
        f"📀 Disk  {_disk()}\n"
        f"📊 Load  {_load_avg()}\n"
        f"⏱ Boot   {_boot_time()}"
    )