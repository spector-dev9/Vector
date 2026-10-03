"""Shell execution with hard limits."""
import asyncio
import os
from pathlib import Path

DEFAULT_TIMEOUT = 20
BLOCKED = (
    "rm -rf /", "rm -rf /*", "dd if=", "mkfs",
    ":(){ :|:& };:", "chmod -R 000 /", "shutdown",
    "reboot", "halt", "poweroff", "> /dev/sda",
)


def is_blocked(cmd):
    low = cmd.lower()
    for pat in BLOCKED:
        if pat.lower() in low:
            return pat
    return None


async def run_shell(cmd, cwd, timeout=DEFAULT_TIMEOUT):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd),
        env=os.environ.copy(),
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"code": -1, "output": "", "timeout": True}
    out = (stdout or b"").decode("utf-8", errors="replace")
    return {"code": proc.returncode, "output": out, "timeout": False}
