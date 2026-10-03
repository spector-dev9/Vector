#!/usr/bin/env python3
"""VECTOR Controller Bot — manage the userbot from Telegram.

Run as a separate process:
    python controller.py

Requires in .env:
    CONTROL_BOT_TOKEN      — a bot token from @BotFather
    CONTROL_BOT_ADMIN_ID   — your Telegram user id (find with @userinfobot)

Provides:
    /start    — spawn the userbot
    /stop     — terminate the userbot
    /restart  — stop + spawn
    /status   — live status panel
    /logs     — tail recent log lines
    /help     — this list
    /panel    — inline-button dashboard

Plus: auto-restart on crash, admin-only, no external shell needed.
"""
import asyncio
import os
import signal
import sys
import time
from pathlib import Path

from telethon import Button, TelegramClient, events
from telethon.errors import MessageNotModifiedError

from Config.settings import Config
from core.logger import setup_logger

logger = setup_logger("VECTOR.controller")

PROJECT_ROOT = Path(__file__).resolve().parent
USERBOT_SCRIPT = PROJECT_ROOT / "main.py"
CONTROLLER_SESSION_DIR = Path(Config.DATA_DIR) / "controller"
CONTROLLER_SESSION_DIR.mkdir(parents=True, exist_ok=True)
CONTROLLER_SESSION = str(CONTROLLER_SESSION_DIR / "session")

# ═══════════════════════════════════════════════════════════════════
#  PROCESS STATE
# ═══════════════════════════════════════════════════════════════════

_proc: asyncio.subprocess.Process | None = None
_started_at: float | None = None
_stop_requested: bool = False
_restart_count: int = 0
_last_exit_code: int | None = None
_notify_chat_id: int | None = None


# ═══════════════════════════════════════════════════════════════════
#  PROCESS OPERATIONS
# ═══════════════════════════════════════════════════════════════════

def _is_running() -> bool:
    return _proc is not None and _proc.returncode is None


async def _spawn() -> tuple[bool, str]:
    global _proc, _started_at
    if _is_running():
        return False, "Userbot is already running."
    if not USERBOT_SCRIPT.exists():
        return False, f"`{USERBOT_SCRIPT}` not found."

    try:
        _proc = await asyncio.create_subprocess_exec(
            sys.executable, "-u", str(USERBOT_SCRIPT),
            cwd=str(PROJECT_ROOT),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        _started_at = time.monotonic()
        logger.info("▶️ userbot started (pid=%s)", _proc.pid)
        return True, f"▶️ Started · pid `{_proc.pid}`"
    except Exception as e:
        logger.error("spawn failed: %s", e, exc_info=True)
        return False, f"Start failed: `{e}`"


async def _stop(timeout: float = 15.0) -> tuple[bool, str]:
    global _proc, _started_at, _last_exit_code
    if _proc is None or _proc.returncode is not None:
        return False, "Userbot is not running."

    proc = _proc
    try:
        proc.terminate()
    except ProcessLookupError:
        _proc = None
        _started_at = None
        return False, "Already exited."

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass

    _last_exit_code = proc.returncode
    _proc = None
    _started_at = None
    logger.info("⏹ userbot stopped (exit=%s)", _last_exit_code)
    return True, f"⏹ Stopped · exit `{_last_exit_code}`"


async def _restart() -> tuple[bool, str]:
    global _restart_count
    if _is_running():
        ok, msg = await _stop()
        if not ok:
            return False, msg
        await asyncio.sleep(1.0)
    _restart_count += 1
    ok, msg = await _spawn()
    if ok:
        return True, f"🔄 Restarted (#{_restart_count}) · {msg}"
    return False, msg


# ═══════════════════════════════════════════════════════════════════
#  STATUS / LOGS
# ═══════════════════════════════════════════════════════════════════

def _uptime() -> str:
    if not _is_running() or _started_at is None:
        return "—"
    total = int(time.monotonic() - _started_at)
    if total < 60:
        return f"{total}s"
    if total < 3600:
        m, s = divmod(total, 60)
        return f"{m}m {s}s"
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m"


def _tail_logs(n: int = 30) -> str:
    d = Path(Config.LOGS_DIR)
    if not d.exists():
        return "(no log dir)"
    files = sorted(
        (p for p in d.rglob("*.log") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return "(no logs)"
    path = files[0]
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
        lines = data.splitlines()[-n:]
        return f"📄 `{path.name}`\n\n" + "\n".join(lines)
    except Exception as e:
        return f"(read failed: {e})"


def _status_text() -> str:
    running = _is_running()
    icon = "🟢" if running else "🔴"
    pid = _proc.pid if running and _proc else "—"
    state = "running" if running else ("crashed" if _last_exit_code and _last_exit_code != 0 else "stopped")
    accounts = ", ".join(Config.ACCOUNTS)
    lines = [
        "🎛 **VECTOR Controller**",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{icon} **Userbot**      `{state}`",
        f"**PID**          `{pid}`",
        f"**Uptime**       `{_uptime()}`",
        f"**Restarts**     `{_restart_count}`",
    ]
    if _last_exit_code is not None and not running:
        lines.append(f"**Last exit**    `{_last_exit_code}`")
    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"**Accounts**     `{accounts}`",
        f"**Auto-restart** `{'paused' if _stop_requested else 'active'}`",
    ]
    return "\n".join(lines)


def _panel_buttons() -> list:
    return [
        [
            Button.inline("▶️ Start", data="ctl:start"),
            Button.inline("⏹ Stop", data="ctl:stop"),
        ],
        [
            Button.inline("🔄 Restart", data="ctl:restart"),
            Button.inline("📊 Status", data="ctl:status"),
        ],
        [
            Button.inline("📄 Logs (30)", data="ctl:logs"),
            Button.inline("♻️ Refresh", data="ctl:refresh"),
        ],
    ]


# ═══════════════════════════════════════════════════════════════════
#  AUTHORIZATION
# ═══════════════════════════════════════════════════════════════════

def _authorized(event) -> bool:
    if not Config.CONTROL_BOT_ADMIN_ID:
        return False
    return event.sender_id == Config.CONTROL_BOT_ADMIN_ID


# ═══════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════

def register_handlers(client: TelegramClient) -> None:

    async def _deny(event):
        try:
            await event.reply("⛔ Not authorized.")
        except Exception:
            pass

    # ── /start ─────────────────────────────────────────────────────
    @client.on(events.NewMessage(pattern=r"^/start(?:@\w+)?(?:\s|$)"))
    async def cmd_start(event):
        if not _authorized(event):
            return await _deny(event)
        global _stop_requested
        _stop_requested = False
        _, msg = await _spawn()
        await event.reply(msg)

    # ── /stop ──────────────────────────────────────────────────────
    @client.on(events.NewMessage(pattern=r"^/stop(?:@\w+)?(?:\s|$)"))
    async def cmd_stop(event):
        if not _authorized(event):
            return await _deny(event)
        global _stop_requested
        _stop_requested = True
        _, msg = await _stop()
        await event.reply(msg)

    # ── /restart ───────────────────────────────────────────────────
    @client.on(events.NewMessage(pattern=r"^/restart(?:@\w+)?(?:\s|$)"))
    async def cmd_restart(event):
        if not _authorized(event):
            return await _deny(event)
        global _stop_requested
        _stop_requested = False
        await event.reply("🔄 Restarting…")
        _, msg = await _restart()
        await event.reply(msg)

    # ── /status ────────────────────────────────────────────────────
    @client.on(events.NewMessage(pattern=r"^/status(?:@\w+)?(?:\s|$)"))
    async def cmd_status(event):
        if not _authorized(event):
            return await _deny(event)
        await event.reply(_status_text(), buttons=_panel_buttons())

    # ── /logs ──────────────────────────────────────────────────────
    @client.on(events.NewMessage(pattern=r"^/logs(?:@\w+)?(?:\s+(\d+))?$"))
    async def cmd_logs(event):
        if not _authorized(event):
            return await _deny(event)
        n = max(1, min(int(event.pattern_match.group(1) or 30), 200))
        text = _tail_logs(n)
        if len(text) > 3800:
            text = text[-3800:]
        await event.reply(f"```\n{text}\n```")

    # ── /panel ─────────────────────────────────────────────────────
    @client.on(events.NewMessage(pattern=r"^/panel(?:@\w+)?(?:\s|$)"))
    async def cmd_panel(event):
        if not _authorized(event):
            return await _deny(event)
        global _notify_chat_id
        _notify_chat_id = event.chat_id
        await event.reply(_status_text(), buttons=_panel_buttons())

    # ── /help ──────────────────────────────────────────────────────
    @client.on(events.NewMessage(pattern=r"^/help(?:@\w+)?(?:\s|$)"))
    async def cmd_help(event):
        if not _authorized(event):
            return await _deny(event)
        await event.reply(
            "🎛 **VECTOR Controller**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Commands:**\n"
            "`/start` — spawn the userbot\n"
            "`/stop` — terminate the userbot\n"
            "`/restart` — stop + spawn\n"
            "`/status` — status panel\n"
            "`/logs [n]` — tail recent lines\n"
            "`/panel` — inline-button dashboard\n"
            "`/help` — this list\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Auto-restart:** userbot respawns on crash\n"
            "**Admin only:** check `CONTROL_BOT_ADMIN_ID`"
        )

    # ── inline buttons ─────────────────────────────────────────────
    @client.on(events.CallbackQuery(pattern=r"^ctl:"))
    async def on_btn(event):
        if not _authorized(event):
            await event.answer("Not authorized.", alert=True)
            return

        action = event.data.decode().split(":", 1)[1]

        try:
            if action == "start":
                global _stop_requested
                _stop_requested = False
                _, msg = await _spawn()
                await event.answer(msg.replace("`", ""), alert=True)
            elif action == "stop":
                _stop_requested = True
                _, msg = await _stop()
                await event.answer(msg.replace("`", ""), alert=True)
            elif action == "restart":
                _stop_requested = False
                _, msg = await _restart()
                await event.answer(msg.replace("`", ""), alert=True)
            elif action == "logs":
                text = _tail_logs(30)
                if len(text) > 3500:
                    text = text[-3500:]
                await event.answer()
                await event.reply(f"```\n{text}\n```")
                return
            elif action in ("status", "refresh"):
                await event.answer()

            # refresh the panel
            try:
                await event.edit(_status_text(), buttons=_panel_buttons())
            except MessageNotModifiedError:
                pass
        except Exception as e:
            logger.error("button %s: %s", action, e, exc_info=True)
            try:
                await event.answer(f"error: {e}", alert=True)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════
#  SUPERVISOR — auto-restart on crash
# ═══════════════════════════════════════════════════════════════════

async def _supervise(client: TelegramClient) -> None:
    global _proc, _started_at, _last_exit_code
    while True:
        await asyncio.sleep(5)
        if _stop_requested:
            continue
        if _proc is not None and _proc.returncode is not None:
            code = _proc.returncode
            _last_exit_code = code
            _proc = None
            _started_at = None
            logger.warning("⚠️ userbot exited (code %s); restarting…", code)

            # notify admin
            if _notify_chat_id or Config.CONTROL_BOT_ADMIN_ID:
                target = _notify_chat_id or Config.CONTROL_BOT_ADMIN_ID
                try:
                    await client.send_message(
                        target,
                        f"⚠️ Userbot exited (code `{code}`). Restarting…",
                    )
                except Exception:
                    pass

            await _spawn()


# ═══════════════════════════════════════════════════════════════════
#  STARTUP / SHUTDOWN
# ═══════════════════════════════════════════════════════════════════

async def _on_sigterm(client: TelegramClient) -> None:
    """Handle graceful shutdown — stop the userbot too."""
    logger.info("🛑 controller shutting down")
    try:
        await _stop()
    except Exception:
        pass
    try:
        await client.disconnect()
    except Exception:
        pass


async def main() -> int:
    if not Config.CONTROL_BOT_TOKEN:
        print("❌ CONTROL_BOT_TOKEN is not set in .env")
        return 1
    if not Config.CONTROL_BOT_ADMIN_ID:
        print("❌ CONTROL_BOT_ADMIN_ID is not set in .env")
        return 1

    print("🎛 VECTOR Controller starting…")
    print(f"   session: {CONTROLLER_SESSION}")
    print(f"   admin:   {Config.CONTROL_BOT_ADMIN_ID}")
    print(f"   accounts: {', '.join(Config.ACCOUNTS)}")

    client = TelegramClient(
        CONTROLLER_SESSION,
        Config.API_ID, Config.API_HASH,
        device_model="VECTOR Controller",
        system_version="Linux",
        app_version=Config.VERSION,
    )

    await client.start(bot_token=Config.CONTROL_BOT_TOKEN)
    me = await client.get_me()
    logger.info("✅ Controller online as @%s", me.username or me.id)

    register_handlers(client)

    # spawn userbot on boot
    _, boot_msg = await _spawn()
    logger.info("userbot: %s", boot_msg)

    # supervise loop
    asyncio.create_task(_supervise(client))

    # hello message
    global _notify_chat_id
    _notify_chat_id = Config.CONTROL_BOT_ADMIN_ID
    try:
        await client.send_message(
            Config.CONTROL_BOT_ADMIN_ID,
            "🎛 **Controller online**\n\n"
            + _status_text(),
            buttons=_panel_buttons(),
        )
    except Exception as e:
        logger.warning("hello message failed: %s", e)

    try:
        await client.run_until_disconnected()
    finally:
        await _on_sigterm(client)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n👋 Controller stopped.")