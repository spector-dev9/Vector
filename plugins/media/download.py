"""Download with SSRF guard + size cap + cleanup."""
import os
import time
from pathlib import Path

import httpx

from core.decorators import command
from core.module import ModuleMeta
from helpers.network.http import is_safe_url
from helpers.telegram.messages import safe_edit
from utils import Messages, Formatters

META = ModuleMeta(
    name="download", category="media",
    description="Download from a URL or replied media to the server.",
    permission="user",
)

MAX_BYTES = 500 * 1024 * 1024


@command(r"download\s+([\S]+)", "Download a URL to the server")
async def download_url(event):
    ctx = event.ctx
    url = event.pattern_match.group(1).strip()
    if not is_safe_url(url):
        await event.edit(Messages.error("Refused: URL is unsafe or private."))
        return
    status = await event.edit(Messages.loading(f"Downloading `{url}`…"))
    target_dir = ctx.paths.sub("downloads")
    name = os.path.basename(url.split("?")[0]) or f"file_{int(time.time())}"
    name = "".join(c for c in name if c.isalnum() or c in "._-")[:120] or f"file_{int(time.time())}"
    target = target_dir / name
    partial = target.with_suffix(target.suffix + ".part")

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            async with c.stream("GET", url) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                if total and total > MAX_BYTES:
                    await event.edit(Messages.error(
                        f"Refused: file too large ({Formatters.format_size(total)})."))
                    return
                done = 0
                last = 0.0
                with open(partial, "wb") as f:
                    async for chunk in r.aiter_bytes(64 * 1024):
                        f.write(chunk)
                        done += len(chunk)
                        if done > MAX_BYTES:
                            raise ValueError("download exceeded size cap")
                        now = time.time()
                        if now - last > 2 and total:
                            last = now
                            await safe_edit(
                                status,
                                f"⬇️ {done/total*100:.0f}% · "
                                f"{Formatters.format_size(done)}/"
                                f"{Formatters.format_size(total)}",
                            )
    except Exception as e:
        try:
            partial.unlink()
        except Exception:
            pass
        await safe_edit(event, Messages.error(str(e)))
        return
    try:
        partial.rename(target)
    except Exception as e:
        await safe_edit(event, Messages.error(str(e)))
        return
    await safe_edit(event, Messages.success(
        f"Saved `{target.name}` · {Formatters.format_size(target.stat().st_size)}\n"
        f"Path: `{target}`"))


@command(r"dlfile", "Save replied media to the server")
async def download_replied(event):
    ctx = event.ctx
    reply = await event.get_reply_message()
    if reply is None or not (reply.document or reply.photo):
        await safe_edit(event, Messages.error("Reply to a file."))
        return
    target_dir = ctx.paths.sub("downloads")
    status = await event.edit(Messages.loading("Downloading…"))
    fpath = await event.client.download_media(reply, file=str(target_dir / "dl"))
    if not fpath:
        await safe_edit(event, Messages.error("Download failed."))
        return
    p = Path(fpath)
    await safe_edit(event, Messages.success(
        f"Saved `{p.name}` · {Formatters.format_size(p.stat().st_size)}\n`{p}`"))
