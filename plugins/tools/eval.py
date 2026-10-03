"""Eval / Exec / Inspect."""
import contextlib
import inspect
import io
import traceback

from core.decorators import command
from core.module import ModuleMeta
from Config.settings import Config
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="eval", category="tools",
    description="Execute Python code and inspect objects.",
    permission="sudo",
)


@command(r"eval\s+([\s\S]+)", "Evaluate a Python expression", permission="sudo")
async def eval_cmd(event):
    ctx = event.ctx
    code = event.pattern_match.group(1)
    scope = {"ctx": ctx, "event": event, "client": event.client,
             "message": event.message, "chat_id": event.chat_id}
    try:
        result = eval(code, {"__builtins__": __builtins__}, scope)
        if inspect.isawaitable(result):
            result = await result
    except Exception:
        result = traceback.format_exc()
    text = str(result)
    if len(text) > 3000:
        text = text[:3000] + "\n…(truncated)"
    await event.edit(f"🧪 **Eval**\n{SEP_FANCY}\n`{code}`\n\n```\n{text}\n```")


@command(r"exec\s+([\s\S]+)", "Execute Python statements", permission="sudo")
async def exec_cmd(event):
    ctx = event.ctx
    code = event.pattern_match.group(1)
    buf = io.StringIO()
    scope = {"ctx": ctx, "event": event, "client": event.client,
             "message": event.message, "chat_id": event.chat_id}
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, {"__builtins__": __builtins__}, scope)
    except Exception:
        buf.write(traceback.format_exc())
    out = buf.getvalue() or "ok"
    if len(out) > 3000:
        out = out[:3000] + "\n…(truncated)"
    await event.edit(f"🧪 **Exec**\n{SEP_FANCY}\n`{code}`\n\n```\n{out}\n```")


@command(r"inspect\s+([\s\S]+)", "Inspect an object/attribute", permission="sudo")
async def inspect_cmd(event):
    expr = event.pattern_match.group(1).strip()
    try:
        obj = eval(expr)
        fields = [a for a in dir(obj) if not a.startswith("_")][:60]
        text = "\n".join(f"• `{f}`" for f in fields)
    except Exception:
        text = traceback.format_exc()
    await event.edit(f"🔍 **Inspect `{expr}`**\n{SEP_FANCY}\n{text}")


@command(r"pysh\s+([\s\S]+)", "Run a shell command", permission="sudo")
async def pysh_cmd(event):
    from helpers.system.shell import run_shell, is_blocked
    cmd = event.pattern_match.group(1).strip()
    if is_blocked(cmd):
        await event.edit(Messages.error("🚫 blocked pattern"))
        return
    res = await run_shell(cmd, Config.BASE_DIR)
    if res["timeout"]:
        await event.edit(Messages.error("⏱ timed out"))
        return
    out = (res["output"] or "")[:3000]
    status = "✅" if res["code"] == 0 else "❌"
    await event.edit(f"{status} **$** `{cmd}`\n_exit {res['code']}_\n```\n{out}\n```")
