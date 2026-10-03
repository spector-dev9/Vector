"""Web — crypto prices, currency, weather, IP info, DNS, HTTP."""
import httpx

from core.decorators import command
from core.module import ModuleMeta
from helpers.network.http import get_json, fetch_text
from utils import Messages

META = ModuleMeta(
    name="web", category="tools",
    description="Crypto prices, currency, weather, IP info, DNS, HTTP.",
    permission="user",
)

_CG = "https://api.coingecko.com/api/v3"
_IDS = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana", "doge": "dogecoin",
    "bnb": "binancecoin", "xrp": "ripple", "ada": "cardano", "ltc": "litecoin",
    "ton": "the-open-network", "usdt": "tether", "usdc": "usd-coin",
}


@command(r"price (\w+)", "Crypto price")
async def price(e):
    raw = e.pattern_match.group(1)
    cg = _IDS.get(raw.lower(), raw.lower())
    await e.edit(Messages.loading(f"Getting {raw}…"))
    d = await get_json(f"{_CG}/simple/price",
                       ids=cg, vs_currencies="usd,inr,eur",
                       include_24hr_change="true")
    if not d or cg not in d:
        await e.edit(Messages.error(f"Unknown `{raw}`."))
        return
    p = d[cg]
    ch = p.get("usd_24h_change", 0) or 0
    arrow = "🟢" if ch >= 0 else "🔴"
    await e.edit(
        f"💎 **{raw.upper()}**\n"
        f"USD `${p.get('usd',0):,.4f}`\n"
        f"INR `₹{p.get('inr',0):,.2f}`\n"
        f"24h {arrow} `{ch:+.2f}%`"
    )


@command("top10", "Top 10 coins")
async def top10(e):
    d = await get_json(f"{_CG}/coins/markets", vs_currency="usd",
                       order="market_cap_desc", per_page=10, page=1,
                       price_change_percentage="24h")
    if not d:
        await e.edit(Messages.error("Fetch failed."))
        return
    lines = ["🏆 **Top 10**", ""]
    for i, c in enumerate(d, 1):
        ch = c.get("price_change_percentage_24h", 0) or 0
        pr = c.get("current_price", 0)
        ps = f"${pr:,.2f}" if pr >= 1 else f"${pr:.6f}"
        arrow = "🟢" if ch >= 0 else "🔴"
        lines.append(f"{i}. **{c['symbol'].upper()}** {ps} {arrow} {ch:+.2f}%")
    await e.edit("\n".join(lines))


@command(r"fx (\w{3}) (\w{3})", "FX rate")
async def fx(e):
    src = e.pattern_match.group(1).upper()
    dst = e.pattern_match.group(2).upper()
    d = await get_json("https://api.frankfurter.app/latest",
                       **{"from": src, "to": dst})
    if not d or dst not in (d.get("rates") or {}):
        await e.edit(Messages.error(f"{src}/{dst} unavailable."))
        return
    await e.edit(f"💱 **1 {src} = {d['rates'][dst]:,.4f} {dst}**")


@command(r"convert (\d+(?:\.\d+)?) (\w{3}) (\w{3})", "Convert amount")
async def convert(e):
    amt = float(e.pattern_match.group(1))
    src = e.pattern_match.group(2).upper()
    dst = e.pattern_match.group(3).upper()
    d = await get_json("https://api.frankfurter.app/latest", amount=amt,
                       **{"from": src, "to": dst})
    if not d or dst not in (d.get("rates") or {}):
        await e.edit(Messages.error("Unavailable."))
        return
    await e.edit(f"💱 **{amt:,.2f} {src}** = **{d['rates'][dst]:,.2f} {dst}**")


@command(r"weather (.+)", "Weather")
async def weather(e):
    city = e.pattern_match.group(1)
    d = await get_json(f"https://wttr.in/{city}", format="j1")
    if not d:
        await e.edit(Messages.error("Failed."))
        return
    try:
        x = d["current_condition"][0]
        await e.edit(
            f"🌤 **{city}**\n{x['weatherDesc'][0]['value']}\n"
            f"Temp {x['temp_C']}°C · Hum {x['humidity']}% · "
            f"Wind {x['windspeedKmph']} km/h"
        )
    except Exception:
        await e.edit(Messages.error("Parse failed."))


@command(r"ip(?: (.+))?", "IP info")
async def ip_cmd(e):
    arg = (e.pattern_match.group(1) or "").strip()
    url = f"https://ipinfo.io/{arg}/json" if arg else "https://ipinfo.io/json"
    d = await get_json(url)
    if not d:
        await e.edit(Messages.error("Lookup failed."))
        return
    parts = [f"🌐 **{d.get('ip','?')}**"]
    for k in ("city", "region", "country", "org", "timezone"):
        if d.get(k):
            parts.append(f"• **{k}:** {d[k]}")
    await e.edit("\n".join(parts))


@command(r"dns (\S+)", "DNS lookup")
async def dns(e):
    domain = e.pattern_match.group(1)
    lines = []
    for t in ("A", "AAAA", "MX", "TXT"):
        d = await get_json("https://dns.google/resolve", name=domain, type=t)
        if not d:
            continue
        for a in (d.get("Answer") or [])[:4]:
            lines.append(f"**{t}** `{a.get('data')}`")
    if not lines:
        await e.edit(Messages.error("No records."))
        return
    await e.edit("\n".join(lines))


@command(r"httpget (\S+)", "HTTP GET")
async def httpget(e):
    u = e.pattern_match.group(1)
    if not u.startswith("http"):
        u = "https://" + u
    txt = await fetch_text(u)
    if txt is None:
        await e.edit(Messages.error("Request failed."))
        return
    await e.edit(f"```\n{txt[:2900]}\n```")


@command(r"shorten (\S+)", "Shorten URL")
async def shorten(e):
    u = e.pattern_match.group(1)
    if not u.startswith("http"):
        u = "https://" + u
    txt = await fetch_text("https://tinyurl.com/api-create.php", url=u)
    if not txt:
        await e.edit(Messages.error("Failed."))
        return
    await e.edit(f"🔗 {txt.strip()}")


@command(r"qr (.+)", "Generate QR")
async def qr(e):
    import io
    text = e.pattern_match.group(1).strip()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.qrserver.com/v1/create-qr-code/",
                            params={"data": text, "size": "512x512", "margin": 10})
            r.raise_for_status()
            buf = io.BytesIO(r.content)
            buf.name = "qr.png"
            await e.client.send_file(e.chat_id, buf, caption=f"🔲 `{text[:80]}`")
            await e.delete()
    except Exception as x:
        await e.edit(Messages.error(f"Failed: {x}"))


@command("webhelp", "Web tools help")
async def webhelp(e):
    await e.edit(
        "🌐 `.price .top10 .fx .convert .weather .ip .dns .httpget .shorten .qr`"
    )
