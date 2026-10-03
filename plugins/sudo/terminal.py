""".sh — shell commands (sudo)."""
from core.decorators import command
from core.module import ModuleMeta
from helpers.system.shell import run_shell, is_blocked
from Config.settings import Config
from utils import Messages

META = ModuleMeta(
    name="terminal", category="sudo",
    description="Run shell commands on the host.",
    permission="sudo",
)

ROOT = Config.BASE_DIR


def _wrap(out):
    out = out.strip() or "(no output)"
    return out if len(out) <= 3400 else out[:3400] + "\n… truncated"


@command(r"sh (.+)", "Run a shell command", permission="sudo")
async def sh(event):
    cmd = event.pattern_match.group(1).strip()
    if is_blocked(cmd):
        await event.edit(Messages.error("🚫 blocked pattern."))
        return
    await event.edit(Messages.loading(f"$ `{cmd}`"))
    res = await run_shell(cmd, ROOT)
    if res["timeout"]:
        await event.edit(Messages.error("Timed out."))
        return
    status = "✅" if res["code"] == 0 else "❌"
    await event.edit(
        f"{status} **$** `{cmd}`\n_exit {res['code']}_\n"
        f"```\n{_wrap(res['output'])}\n```"
    )
