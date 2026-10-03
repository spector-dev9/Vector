"""tester — automated command smoke test harness.

Two modes:
  .testall send     — send every command to Saved Messages, don't wait
                     or verify. You scroll Saved Messages and see which
                     ones replied. Fastest way to visually audit.
  .testall verify   — send each command, wait, read back the response,
                     and report pass/fail inline.
  .testall quick    — send-only, safe commands only (skip network)
  .testsend <cmd>   — send ONE command to Saved Messages
"""
import asyncio

from core.decorators import command
from core.module import ModuleMeta
from utils import Messages, SEP_FANCY
from helpers.formatting.animator import set_enabled as anim_set, enabled as anim_get

META = ModuleMeta(
    name="tester", category="developer",
    description="Automated command smoke test harness.",
    permission="sudo",
)

TARGET_USER = "@Sabyasachi126"
TARGET_ID = "8298261686"

# (command, kind)  kind: safe | net | target
TESTS = [
    # ── ping ────────────────────────────────────────────
    ("ping", "net"),
    ("p", "net"),
    ("alive", "safe"),

    # ── sudo ────────────────────────────────────────────
    ("status", "safe"),
    ("root", "safe"),
    ("modhealth", "safe"),
    ("modlist", "safe"),
    ("lsfile", "safe"),
    ("lsfile plugins", "safe"),
    ("lsfile helpers/telegram", "safe"),
    ("readfile README.md", "safe"),
    ("sh pwd", "safe"),
    ("sh whoami", "safe"),

    # ── root ────────────────────────────────────────────
    ("info", "safe"),
    ("whois", "safe"),
    ("getid", "safe"),
    ("chatid", "safe"),
    ("uname", "safe"),
    ("bio", "safe"),
    ("name", "safe"),

    # ── telegram ────────────────────────────────────────
    ("cinfo", "safe"),
    ("cwhois", "safe"),
    ("cgetid", "safe"),
    ("cchatid", "safe"),

    # ── account ─────────────────────────────────────────
    ("notes", "safe"),
    ("presets", "safe"),

    # ── automation ──────────────────────────────────────
    ("afk test", "safe"),
    ("unafk", "safe"),
    ("filters", "safe"),
    ("ghost", "safe"),
    ("aion", "safe"),
    ("aimood", "safe"),
    ("myschedule", "safe"),
    ("tracked", "safe"),
    ("listwelcome", "safe"),
    ("pmguard", "safe"),
    ("listapproved", "safe"),

    # ── media ───────────────────────────────────────────
    ("getthumb", "safe"),

    # ── sessionkiller ───────────────────────────────────
    ("sessionkiller", "safe"),
    ("authsessions", "safe"),

    # ── text ────────────────────────────────────────────
    ("upper hello", "safe"),
    ("lower HELLO", "safe"),
    ("titlecase hello world", "safe"),
    ("swapcase HeLLo", "safe"),
    ("capital hello", "safe"),
    ("reverse abc", "safe"),
    ("leet test", "safe"),
    ("rot13 hello", "safe"),
    ("tcount hello world", "safe"),
    ("password 16", "safe"),
    ("uuid", "safe"),
    ("token 16", "safe"),
    ("hash md5 test", "safe"),
    ("hash sha256 test", "safe"),
    ("b64enc hello", "safe"),
    ("b64dec aGVsbG8=", "safe"),
    ("urlenc hello world", "safe"),
    ("urldec hello%20world", "safe"),
    ("hex hello", "safe"),
    ("unhex 68656c6c6f", "safe"),
    ("epoch", "safe"),
    ("epoch 1700000000", "safe"),

    # ── math ────────────────────────────────────────────
    ("roman 2024", "safe"),
    ("unroman MMXXIV", "safe"),
    ("tobase 255 16", "safe"),
    ("frombase ff 16", "safe"),
    ("temp 100 c", "safe"),
    ("percent 10 50", "safe"),
    ("aspect 1920 1080", "safe"),
    ("prime 17", "safe"),
    ("factorial 5", "safe"),
    ("fib 10", "safe"),
    ("color #ff5733", "safe"),
    ("rgb 255 87 51", "safe"),
    ("randomcolor", "safe"),

    # ── web ─────────────────────────────────────────────
    ("price btc", "net"),
    ("top10", "net"),
    ("fx USD EUR", "net"),
    ("convert 100 USD EUR", "net"),
    ("ip", "net"),
    ("dns google.com", "net"),
    ("httpget example.com", "net"),
    ("shorten example.com", "net"),

    # ── eval ────────────────────────────────────────────
    ("eval 2+2", "safe"),
    ("exec x=1", "safe"),
    ("inspect [1,2,3]", "safe"),
    ("pysh echo hi", "safe"),

    # ── developer ───────────────────────────────────────
    ("selftest", "safe"),
    ("cmds", "safe"),
    ("count", "safe"),
    ("errors", "safe"),

    # ── fun ─────────────────────────────────────────────
    ("coinflip", "safe"),
    ("8ball hello", "safe"),
    ("rps rock", "safe"),
    ("gstats", "safe"),
    ("vexhelp", "safe"),
    ("fakeme hello", "safe"),
    ("faketag test hello", "safe"),
    ("reverse_ abc", "safe"),
    ("uwu hello", "safe"),
    ("clap hello world", "safe"),
    ("snipe", "safe"),

    # ── system ──────────────────────────────────────────
    ("help", "safe"),
    ("help tools", "safe"),
    ("help ping", "safe"),
    ("loglist", "safe"),
    ("loghelp", "safe"),

    # ── target (needs a real user) ──────────────────────
    (f"cinfo {TARGET_USER}", "target"),
    (f"cwhois {TARGET_USER}", "target"),
    (f"cgetid {TARGET_USER}", "target"),
    (f"cgetid {TARGET_ID}", "target"),
]


# ══════════════════════════════════════════════════════════════
#  send-only mode — simplest, most reliable
# ══════════════════════════════════════════════════════════════

@command(r"testall(?:\s+(send|quick|verify|target))?", "Run smoke tests",
         permission="sudo")
async def testall(event):
    mode = (event.pattern_match.group(1) or "send").lower()

    if mode == "verify":
        await _verify_all(event)
    elif mode == "quick":
        await _send_all(event, kinds={"safe"})
    elif mode == "target":
        await _send_all(event, kinds={"target"})
    else:  # "send" (default)
        await _send_all(event, kinds={"safe", "net"})


async def _send_all(event, kinds):
    cmds = [c for c, k in TESTS if k in kinds]
    total = len(cmds)

    # disable typing animation for the whole run
    was_on = anim_get()
    anim_set(False)

    await event.edit(
        f"📤 **Sending {total} commands to Saved Messages…**\n"
        f"{SEP_FANCY}\n"
        f"Kind: `{', '.join(sorted(kinds))}`\n"
        f"Delay: 1.2s between sends\n\n"
        f"_Results will be visible in Saved Messages._"
    )
    await asyncio.sleep(0.4)

    sent = 0
    send_errors = []

    try:
        for i, cmd in enumerate(cmds, 1):
            try:
                await event.client.send_message("me", f".{cmd}")
                sent += 1
            except Exception as e:
                send_errors.append(f"{cmd}: {type(e).__name__}: {e}")

            await asyncio.sleep(1.2)

            # progress every 15 commands
            if i % 15 == 0 or i == total:
                try:
                    await event.edit(
                        f"📤 **Sending…** {i}/{total}\n"
                        f"{SEP_FANCY}\n"
                        f"✅ sent: **{sent}**\n"
                        f"❌ send errors: **{len(send_errors)}**\n"
                        f"_current: `.{cmd}`_"
                    )
                except Exception:
                    pass
    finally:
        anim_set(was_on)

    lines = [
        "📤 **Send complete**",
        SEP_FANCY,
        f"Sent: **{sent}/{total}**",
        f"Send errors: **{len(send_errors)}**",
        SEP_FANCY,
        "**What to do now:**",
        "1. Open Saved Messages",
        "2. Scroll through the recent messages",
        "3. Any line that still shows `.cmdname` means the handler did NOT reply.",
        "4. Any line that was replaced with a real answer = command works.",
        "",
        "_Share the list of stuck commands and we fix each one._",
    ]
    if send_errors:
        lines.append("\n**Send errors:**")
        for e in send_errors[:10]:
            lines.append(f"❌ {e}")

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n_…truncated_"
    await event.edit(text)


# ══════════════════════════════════════════════════════════════
#  verify mode — send + read back, per-command verdict
# ══════════════════════════════════════════════════════════════

async def _verify_all(event):
    cmds = [(c, k) for c, k in TESTS]
    total = len(cmds)

    was_on = anim_get()
    anim_set(False)

    await event.edit(
        f"🧪 **Verify mode — {total} tests**\n"
        f"{SEP_FANCY}\n"
        f"_Will take ~{total * 4 // 60} min {total * 4 % 60}s._"
    )
    await asyncio.sleep(0.4)

    results = []
    pass_n = fail_n = warn_n = 0

    try:
        for i, (cmd, kind) in enumerate(cmds, 1):
            wait = 4.5 if kind == "net" else 3.0
            verdict, detail = await _run_one(event.client, cmd, wait)

            if verdict == "pass":
                pass_n += 1
            elif verdict == "fail":
                fail_n += 1
            else:
                warn_n += 1
            results.append((cmd, verdict, detail[:90]))

            if i % 5 == 0 or i == total:
                try:
                    await event.edit(
                        f"🧪 **Verify {i}/{total}**\n"
                        f"{SEP_FANCY}\n"
                        f"✅ {pass_n}   ❌ {fail_n}   ⚠️ {warn_n}\n"
                        f"_current: `.{cmd}`_"
                    )
                except Exception:
                    pass
    finally:
        anim_set(was_on)

    lines = [
        "🧪 **Verify complete**",
        SEP_FANCY,
        f"Total: **{total}**",
        f"✅ pass: **{pass_n}**",
        f"❌ fail: **{fail_n}**",
        f"⚠️ warn: **{warn_n}**",
        SEP_FANCY,
    ]
    shown = 0
    for cmd, verdict, detail in results:
        if verdict == "pass":
            continue
        icon = "❌" if verdict == "fail" else "⚠️"
        lines.append(f"{icon} `{cmd}` — _{detail}_")
        shown += 1
        if shown >= 35:
            lines.append("_…truncated_")
            break
    if shown == 0:
        lines.append("✅ Every command responded cleanly.")

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n_…truncated_"
    await event.edit(text)


async def _run_one(client, cmd_text, wait):
    """Send one command, wait, read back. Does NOT delete messages."""
    sent = None
    try:
        sent = await client.send_message("me", f".{cmd_text}")
    except Exception as e:
        return "fail", f"send failed: {type(e).__name__}: {e}"

    await asyncio.sleep(wait)

    # read back by id — this gets the edited message or the original
    text = ""
    try:
        refreshed = await client.get_messages("me", ids=sent.id)
        text = (refreshed.raw_text or "") if refreshed else ""
    except Exception as e:
        return "warn", f"readback failed: {type(e).__name__}"

    # if the message was edited by the handler, it's not the original command
    if text and text != f".{cmd_text}":
        return _classify(text)

    # otherwise look for a follow-up reply right after
    try:
        followups = []
        async for m in client.iter_messages(
            "me", min_id=sent.id, limit=5, reverse=True
        ):
            followups.append(m)
        if followups:
            return _classify(followups[0].raw_text or "(media)")
    except Exception:
        pass

    return "fail", "(no response)"


def _classify(text):
    r = (text or "").strip()
    if not r:
        return "fail", "(empty)"
    if "❌" in r:
        return "fail", r
    if "⛔" in r:
        return "fail", r
    if r.startswith("⏳"):
        return "warn", r
    return "pass", r


# ══════════════════════════════════════════════════════════════
#  single-command helper
# ══════════════════════════════════════════════════════════════

@command(r"testsend (.+)", "Send ONE command to Saved Messages (manual test)",
         permission="sudo")
async def testsend(event):
    cmd = event.pattern_match.group(1).strip()
    try:
        await event.client.send_message("me", f".{cmd}")
    except Exception as e:
        await event.edit(Messages.error(f"send failed: {e}"))
        return
    await event.edit(
        f"📤 Sent `.{cmd}` to Saved Messages.\n"
        f"_Check there for the reply._"
    )


@command("testerhelp", "Tester help")
async def testerhelp(event):
    await event.edit(
        "🧪 **TESTER**\n"
        f"{SEP_FANCY}\n\n"
        "**Send-only** (you verify manually):\n"
        "▸ `.testall send` — every safe + network command\n"
        "▸ `.testall quick` — safe commands only, no network\n"
        "▸ `.testall target` — only commands needing @user\n\n"
        "**Verify** (tester checks the reply):\n"
        "▸ `.testall verify` — send + wait + classify per-command\n\n"
        "**Single** (fire one command):\n"
        "▸ `.testsend <command>` — e.g. `.testsend ping`\n\n"
        "**How to read send-only results:**\n"
        "Open Saved Messages. Every line is either:\n"
        "• the original `.cmdname` — handler did NOT respond\n"
        "• the real answer — command works"
    )