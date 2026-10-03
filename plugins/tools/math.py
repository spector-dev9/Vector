"""Math / colors."""
import colorsys
import math
import random

from core.decorators import command
from core.module import ModuleMeta
from utils import Messages

META = ModuleMeta(
    name="math", category="tools",
    description="Numbers, math, base conversions, colors.",
    permission="user",
)

_ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
          (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
          (5, "V"), (4, "IV"), (1, "I")]


def _hex(r, g, b):
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}"


def _rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


@command(r"roman (\d+)", "Decimal → Roman")
async def roman(e):
    n = int(e.pattern_match.group(1))
    out = ""
    for v, s in _ROMAN:
        out += s * (n // v)
        n %= v
    await e.edit(f"`{out}`")


@command(r"unroman ([IVXLCDMivxlcdm]+)", "Roman → Decimal")
async def unroman(e):
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    s = e.pattern_match.group(1).upper()
    n = prev = 0
    for c in reversed(s):
        x = v[c]
        n += -x if x < prev else x
        prev = max(prev, x)
    await e.edit(f"**{n}**")


@command(r"tobase (\d+) (\d+)", "Decimal → base N")
async def tobase(e):
    n = int(e.pattern_match.group(1))
    b = int(e.pattern_match.group(2))
    if not 2 <= b <= 36:
        await e.edit(Messages.error("Base 2–36."))
        return
    d = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = "0" if n == 0 else ""
    while n:
        out = d[n % b] + out
        n //= b
    await e.edit(f"`{out}`")


@command(r"frombase (\w+) (\d+)", "Base N → Decimal")
async def frombase(e):
    try:
        out = int(e.pattern_match.group(1), int(e.pattern_match.group(2)))
    except Exception as x:
        await e.edit(Messages.error(str(x)))
        return
    await e.edit(f"**{out}**")


@command(r"temp (-?\d+(?:\.\d+)?) ?([cfkCFK]?)", "Temperature")
async def temp(e):
    v = float(e.pattern_match.group(1))
    u = (e.pattern_match.group(2) or "C").upper()
    c = v if u == "C" else (v - 32) * 5 / 9 if u == "F" else v - 273.15
    await e.edit(f"🌡 `{c:.2f}°C` `{c*9/5+32:.2f}°F` `{c+273.15:.2f}K`")


@command(r"percent (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)", "Percent")
async def percent(e):
    p, n = (float(x) for x in e.pattern_match.groups())
    await e.edit(f"**{p*n/100:g}**")


@command(r"aspect (\d+) (\d+)", "Aspect ratio")
async def aspect(e):
    a = int(e.pattern_match.group(1))
    b = int(e.pattern_match.group(2))
    g = math.gcd(a, b)
    await e.edit(f"`{a//g}:{b//g}`")


@command(r"prime (\d+)", "Prime check")
async def prime(e):
    n = int(e.pattern_match.group(1))
    ok = n > 1 and all(n % i for i in range(2, int(n ** .5) + 1))
    await e.edit("✅ prime" if ok else "❌ not prime")


@command(r"factorial (\d+)", "Factorial")
async def factorial(e):
    await e.edit(f"`{math.factorial(int(e.pattern_match.group(1)))}`")


@command(r"fib (\d+)", "Fibonacci")
async def fib(e):
    a, b = 0, 1
    for _ in range(int(e.pattern_match.group(1))):
        a, b = b, a + b
    await e.edit(f"`{a}`")


@command(r"color (#?\w+)", "Color info")
async def color(e):
    try:
        r, g, b = _rgb(e.pattern_match.group(1))
    except Exception:
        await e.edit(Messages.error("Invalid hex."))
        return
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    await e.edit(
        f"🎨 **{_hex(r, g, b)}**\n"
        f"RGB `rgb({r},{g},{b})`\n"
        f"HSL `hsl({int(h*360)},{int(s*100)}%,{int(l*100)}%)`"
    )


@command(r"rgb (\d+) (\d+) (\d+)", "RGB → hex")
async def rgb(e):
    v = tuple(int(x) for x in e.pattern_match.groups())
    if not all(0 <= x <= 255 for x in v):
        await e.edit(Messages.error("0–255."))
        return
    await e.edit(f"🎨 `{_hex(*v)}`")


@command("randomcolor", "Random color")
async def randomcolor(e):
    await e.edit(f"🎨 `{_hex(*(random.randrange(256) for _ in range(3)))}`")


@command("mathhelp", "Math help")
async def mathhelp(e):
    await e.edit(
        "🔢 `.roman .unroman .tobase .frombase .temp .percent .aspect "
        ".prime .factorial .fib .color .rgb .randomcolor`"
    )
