"""Text — case, ciphers, hashes, encodings."""
import base64
import binascii
import codecs
import hashlib
import secrets
import string
import urllib.parse
import uuid
from datetime import datetime, timezone

from core.decorators import command
from core.module import ModuleMeta
from utils import Messages

META = ModuleMeta(
    name="text", category="tools",
    description="Text transformations, ciphers, hashes, encodings.",
    permission="user",
)

_LEET = str.maketrans({
    "a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7", "b": "8", "g": "9",
    "A": "4", "E": "3", "I": "1", "O": "0", "S": "5", "T": "7", "B": "8", "G": "9",
})


@command(r"upper (.+)", "Uppercase")
async def upper(e):
    await e.edit(e.pattern_match.group(1).upper())


@command(r"lower (.+)", "Lowercase")
async def lower(e):
    await e.edit(e.pattern_match.group(1).lower())


@command(r"titlecase (.+)", "Title case")
async def titlecase(e):
    await e.edit(e.pattern_match.group(1).title())


@command(r"swapcase (.+)", "Swap case")
async def swapcase(e):
    await e.edit(e.pattern_match.group(1).swapcase())


@command(r"capital (.+)", "Capitalize")
async def capital(e):
    await e.edit(e.pattern_match.group(1).capitalize())


@command(r"reverse (.+)", "Reverse text")
async def reverse(e):
    await e.edit(e.pattern_match.group(1)[::-1])


@command(r"leet (.+)", "1337 sp34k")
async def leet(e):
    await e.edit(e.pattern_match.group(1).translate(_LEET))


@command(r"rot13 (.+)", "ROT13")
async def rot13(e):
    await e.edit(f"`{codecs.encode(e.pattern_match.group(1), 'rot_13')}`")


@command(r"tcount (.+)", "Count chars/words/lines")
async def tcount(e):
    t = e.pattern_match.group(1)
    await e.edit(f"chars: {len(t)} · words: {len(t.split())} · "
                 f"lines: {t.count(chr(10))+1}")


@command(r"password(?:\s+(\d+))?", "Generate a password")
async def password(e):
    n = int(e.pattern_match.group(1) or 20)
    n = max(4, min(n, 128))
    pool = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}"
    await e.edit(f"🔐 `{''.join(secrets.choice(pool) for _ in range(n))}`")


@command("uuid", "UUID4")
async def uuid_cmd(e):
    await e.edit(f"🆔 `{uuid.uuid4()}`")


@command(r"token(?:\s+(\d+))?", "Random token")
async def token(e):
    n = int(e.pattern_match.group(1) or 32)
    await e.edit(f"🎫 `{secrets.token_hex(n // 2)}`")


@command(r"hash (md5|sha1|sha256|sha512) (.+)", "Hash")
async def hash_cmd(e):
    a, t = e.pattern_match.group(1), e.pattern_match.group(2)
    await e.edit(f"**{a}**\n`{hashlib.new(a, t.encode()).hexdigest()}`")


@command(r"b64enc (.+)", "Base64 encode")
async def b64enc(e):
    await e.edit("`" + base64.b64encode(e.pattern_match.group(1).encode()).decode() + "`")


@command(r"b64dec (.+)", "Base64 decode")
async def b64dec(e):
    try:
        out = base64.b64decode(e.pattern_match.group(1)).decode(errors="replace")
    except Exception as x:
        await e.edit(Messages.error(str(x)))
        return
    await e.edit(f"`{out}`")


@command(r"urlenc (.+)", "URL encode")
async def urlenc(e):
    await e.edit(f"`{urllib.parse.quote(e.pattern_match.group(1))}`")


@command(r"urldec (.+)", "URL decode")
async def urldec(e):
    await e.edit(f"`{urllib.parse.unquote(e.pattern_match.group(1))}`")


@command(r"hex (.+)", "Text → hex")
async def hex_cmd(e):
    await e.edit(f"`{binascii.hexlify(e.pattern_match.group(1).encode()).decode()}`")


@command(r"unhex (.+)", "Hex → text")
async def unhex(e):
    try:
        out = binascii.unhexlify(e.pattern_match.group(1)).decode(errors="replace")
    except Exception as x:
        await e.edit(Messages.error(str(x)))
        return
    await e.edit(f"`{out}`")


@command(r"epoch(?:\s+(\d+))?", "Unix time")
async def epoch(e):
    a = e.pattern_match.group(1)
    if a:
        try:
            ts = datetime.fromtimestamp(int(a), timezone.utc)
            await e.edit(f"🕒 `{a}` → `{ts:%Y-%m-%d %H:%M:%S}` UTC")
        except Exception as x:
            await e.edit(Messages.error(str(x)))
        return
    await e.edit(f"🕒 `{int(datetime.now(timezone.utc).timestamp())}`")


@command("texthelp", "Text help")
async def texthelp(e):
    await e.edit("📝 `.upper .lower .titlecase .swapcase .capital .reverse .leet .rot13 "
                 ".tcount .password .uuid .token .hash .b64enc .b64dec .urlenc .urldec "
                 ".hex .unhex .epoch`")
