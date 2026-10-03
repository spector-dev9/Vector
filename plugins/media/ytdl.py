"""YouTube download."""
import asyncio
import os
from pathlib import Path

from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo

from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, Formatters

META = ModuleMeta(
    name="ytdl", category="media",
    description="Download audio/video from YouTube and 1000+ other sites.",
    permission="user",
)


def _progress_hook(status_msg, loop):
    last = {"t": 0.0}

    def hook(d):
        import time
        now = time.time()
        if now - last["t"] < 2:
            return
        last["t"] = now
        if d.get("status") != "downloading":
            return
        done = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        if total:
            pct = done / total * 100
            txt = (f"⬇️ {pct:.0f}% · "
                   f"{Formatters.format_size(done)}/"
                   f"{Formatters.format_size(total)}")
            asyncio.run_coroutine_threadsafe(_safe_edit(status_msg, txt), loop)

    return hook


async def _safe_edit(msg, text):
    try:
        await msg.edit(text)
    except Exception:
        pass


async def _download(url, mode, target_dir, status_msg):
    import yt_dlp
    out = str(target_dir / "%(title)s.%(ext)s")
    loop = asyncio.get_running_loop()
    opts = {
        "outtmpl": out,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "quiet": True,
        "progress_hooks": [_progress_hook(status_msg, loop)],
    }
    if mode == "audio":
        opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        opts.update({"format": "best[height<=720]/best"})

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            if mode == "audio":
                path = os.path.splitext(path)[0] + ".mp3"
            return info, path

    info, path = await asyncio.to_thread(_run)
    return info, Path(path)


@command(r"yta\s+([\S]+)", "Download YouTube audio")
async def yta(event):
    ctx = event.ctx
    url = event.pattern_match.group(1).strip()
    status = await event.edit(Messages.loading("Downloading audio…"))
    target = ctx.paths.sub("ytdl")
    try:
        info, path = await _download(url, "audio", target, status)
    except Exception as e:
        await event.edit(Messages.error(str(e)))
        return
    try:
        await event.client.send_file(
            event.chat_id, str(path),
            caption=f"**{info.get('title','audio')}**",
            attributes=[DocumentAttributeAudio(
                duration=int(info.get("duration") or 0),
                title=info.get("title") or "",
                performer=info.get("uploader") or "",
            )],
        )
        os.remove(path)
        await status.delete()
    except Exception as e:
        await event.edit(Messages.error(str(e)))


@command(r"ytv\s+([\S]+)", "Download YouTube video")
async def ytv(event):
    ctx = event.ctx
    url = event.pattern_match.group(1).strip()
    status = await event.edit(Messages.loading("Downloading video…"))
    target = ctx.paths.sub("ytdl")
    try:
        info, path = await _download(url, "video", target, status)
    except Exception as e:
        await event.edit(Messages.error(str(e)))
        return
    try:
        await event.client.send_file(
            event.chat_id, str(path),
            caption=f"**{info.get('title','video')}**",
            attributes=[DocumentAttributeVideo(
                duration=int(info.get("duration") or 0),
                w=int(info.get("width") or 0),
                h=int(info.get("height") or 0),
                supports_streaming=True,
            )],
            supports_streaming=True,
        )
        os.remove(path)
        await status.delete()
    except Exception as e:
        await event.edit(Messages.error(str(e)))


@command(r"yts\s+([\s\S]+)", "YouTube search")
async def yts(event):
    from yt_dlp import YoutubeDL
    q = event.pattern_match.group(1).strip()
    await event.edit(Messages.loading(f"Searching `{q}`…"))

    def _run():
        with YoutubeDL({"quiet": True, "skip_download": True,
                        "extract_flat": True}) as ydl:
            return ydl.extract_info(f"ytsearch10:{q}", download=False)

    try:
        data = await asyncio.to_thread(_run)
    except Exception as e:
        await event.edit(Messages.error(str(e)))
        return
    lines = [f"🔍 **{q}**", ""]
    for i, e in enumerate(data.get("entries", [])[:10], 1):
        lines.append(f"{i}. [{e.get('title','?')}](https://youtu.be/{e.get('id','')})")
    await event.edit("\n".join(lines))
