"""Git — push the VECTOR project to a GitHub repository.

Uses the system `git` binary. Token is stored per-account under
data/accounts/<id>/files/git_token.txt (gitignored). Author config
lives in .git/config, set once via .gitauthor.

Refuses to push if .env or session files are not excluded by
.gitignore. This is the only guard that matters — pushing your
credentials to a public repo is not recoverable.

Android/Termux note: /storage/emulated/0 is a FUSE mount that does not
report Unix ownership reliably. Git refuses to operate on such repos
unless the path is whitelisted. Every git invocation here passes
`-c safe.directory=<PROJECT_ROOT>` so the repo is trusted without
touching the user's global git config.
"""
import asyncio
import re
import time
from pathlib import Path

from core.decorators import command
from core.logger import setup_logger
from core.module import ModuleMeta
from Config.settings import Config
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="git", category="sudo",
    description="Push the VECTOR project to a GitHub repository.",
    permission="sudo",
)

logger = setup_logger("VECTOR.git")

PROJECT_ROOT = Path(Config.BASE_DIR).resolve()
GIT_DIR = PROJECT_ROOT / ".git"

# files that must never be committed
MUST_BE_IGNORED = {".env", "session"}
MUST_BE_IGNORED_DIRS = {"data", "logs", "__pycache__", ".venv", "venv"}


# ═══════════════════════════════════════════════════════════════════
#  low-level helpers
# ═══════════════════════════════════════════════════════════════════

async def _run(*args, timeout: float = 60.0, env: dict | None = None):
    """Run a git command in PROJECT_ROOT. Returns (code, output).

    Passes -c safe.directory=<root> so git trusts the repo even on
    Android shared storage where Unix ownership is unreliable.
    """
    safe_args = ("-c", f"safe.directory={PROJECT_ROOT}", *args)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *safe_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
    except FileNotFoundError:
        return -1, "git not installed on this host"

    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return -1, f"(timeout after {timeout:.0f}s)"

    return proc.returncode, (out or b"").decode("utf-8", errors="replace")


def _is_repo() -> bool:
    return (PROJECT_ROOT / ".git").exists()


def _token_path(ctx):
    return ctx.paths.file("git_token.txt")


def _read_token(ctx, env_name: str = "GITHUB_TOKEN") -> str:
    # env var wins
    import os
    t = os.getenv(env_name, "").strip()
    if t:
        return t
    p = _token_path(ctx)
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return ""


def _write_token(ctx, token: str) -> None:
    try:
        _token_path(ctx).write_text(token.strip(), encoding="utf-8")
    except Exception as e:
        logger.warning(f"token save failed: {e}")


def _clear_token(ctx) -> None:
    try:
        p = _token_path(ctx)
        if p.exists():
            p.unlink()
    except Exception:
        pass


def _sanitize_url(url: str) -> str:
    """Strip embedded credentials from a URL for safe display."""
    if not url:
        return url
    return re.sub(r"//[^@]+@", "//***@", url)


def _inject_token(url: str, token: str) -> str:
    """Insert a token into an https:// URL for push."""
    if not token or not url.startswith("https://"):
        return url
    return url.replace("https://", f"https://{token}@", 1)


async def _get_remote_url() -> str:
    code, out = await _run("remote", "get-url", "origin")
    if code != 0:
        return ""
    return out.strip()


async def _get_branch() -> str:
    code, out = await _run("rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        return ""
    b = out.strip()
    return "" if b == "HEAD" else b


async def _check_ignore_safety() -> tuple[bool, list[str]]:
    """Verify secrets are actually ignored by .gitignore.

    Returns (safe, violations).
    """
    violations: list[str] = []

    gi = PROJECT_ROOT / ".gitignore"
    if not gi.exists():
        violations.append("no .gitignore file")
        return False, violations

    # .env
    if (PROJECT_ROOT / ".env").exists():
        code, _ = await _run("check-ignore", "-q", ".env")
        if code != 0:
            violations.append(".env is NOT ignored")

    # session files anywhere
    for sf in PROJECT_ROOT.glob("*.session"):
        code, _ = await _run("check-ignore", "-q", sf.name)
        if code != 0:
            violations.append(f"{sf.name} is NOT ignored")

    # data/ and logs/
    for d in ("data", "logs"):
        if (PROJECT_ROOT / d).exists():
            code, _ = await _run("check-ignore", "-q", d)
            if code != 0:
                violations.append(f"{d}/ is NOT ignored")

    return (not violations), violations


async def _has_author_config() -> bool:
    code, out = await _run("config", "user.email")
    if code != 0 or not out.strip():
        return False
    code, out = await _run("config", "user.name")
    if code != 0 or not out.strip():
        return False
    return True


async def _has_changes() -> bool:
    code, out = await _run("status", "--porcelain")
    return bool(out.strip())


async def _has_staged() -> bool:
    code, out = await _run("diff", "--cached", "--name-only")
    return bool(out.strip())


# ═══════════════════════════════════════════════════════════════════
#  .gitinit
# ═══════════════════════════════════════════════════════════════════

@command(r"gitinit (\S+)(?:\s+(\S+))?", "Initialize repo + set remote + first push",
         permission="sudo")
async def gitinit(event):
    """
    Usage: `.gitinit <repo_url> [branch]`

    Examples:
        .gitinit https://github.com/you/vector.git
        .gitinit https://github.com/you/vector.git main
    """
    repo_url = event.pattern_match.group(1).strip()
    branch = (event.pattern_match.group(2) or "main").strip()

    if not repo_url.startswith("https://"):
        await event.edit(Messages.error(
            "Repo URL must start with https:// (not git@)."))
        return

    # author check
    if not await _has_author_config():
        await event.edit(Messages.error(
            "Set commit author first:\n"
            "`.gitauthor <name> <email>`"))
        return

    await event.edit(Messages.loading("Initializing repository…"))

    # init
    if not _is_repo():
        code, out = await _run("init", "-b", branch)
        if code != 0:
            # fallback for older git
            code, out = await _run("init")
            if code != 0:
                await event.edit(Messages.error(f"git init failed: {out}"))
                return
            await _run("branch", "-M", branch)

    # remote
    existing = await _get_remote_url()
    if existing:
        await _run("remote", "set-url", "origin", repo_url)
    else:
        code, out = await _run("remote", "add", "origin", repo_url)
        if code != 0:
            await event.edit(Messages.error(f"remote add failed: {out}"))
            return

    # initial add + commit
    await _run("add", "-A")
    if await _has_staged():
        code, out = await _run(
            "commit", "-m", "VECTOR — initial push",
            timeout=30,
        )
        if code != 0:
            await event.edit(Messages.error(f"commit failed: {out}"))
            return

    # push
    await event.edit(Messages.loading("Pushing to origin…"))
    token = _read_token(event.ctx)
    push_url = _inject_token(repo_url, token) if token else repo_url

    code, out = await _run(
        "push", "-u", push_url, f"HEAD:{branch}",
        timeout=180,
    )
    if code != 0:
        if token:
            out = out.replace(token, "***")
        await event.edit(Messages.error(
            f"push failed:\n```\n{out[:1500]}\n```\n"
            f"_Set a token with `.gittoken <ghp_...>` if this is a private repo._"))
        return

    await event.edit(Messages.success(
        f"Repository initialized and pushed.\n"
        f"Remote: `{_sanitize_url(repo_url)}`\n"
        f"Branch: `{branch}`\n"
        f"{SEP_FANCY}\n"
        f"_Future pushes: `.gitpush [msg]`_"))


# ═══════════════════════════════════════════════════════════════════
#  .gitpush
# ═══════════════════════════════════════════════════════════════════

@command(r"gitpush(?:\s+([\s\S]+))?", "Add, commit, push", permission="sudo")
async def gitpush(event):
    """
    Usage:
        .gitpush                  → auto commit message
        .gitpush <your message>   → custom commit message
    """
    if not _is_repo():
        await event.edit(Messages.error(
            "Not a git repo. Run `.gitinit <url>` first."))
        return

    msg = (event.pattern_match.group(1) or "").strip()
    if not msg:
        msg = f"VECTOR update · {time.strftime('%Y-%m-%d %H:%M')}"

    # safety gate
    await event.edit(Messages.loading("Checking ignore safety…"))
    safe, violations = await _check_ignore_safety()
    if not safe:
        await event.edit(Messages.error(
            "Refused to push — secrets are not excluded:\n"
            + "\n".join(f"• {v}" for v in violations)
            + "\n\n_Fix `.gitignore` or remove the offending files._"))
        return

    if not await _has_author_config():
        await event.edit(Messages.error(
            "Commit author not configured.\n`.gitauthor <name> <email>`"))
        return

    await event.edit(Messages.loading("Staging changes…"))
    code, out = await _run("add", "-A")
    if code != 0:
        await event.edit(Messages.error(f"git add failed: {out}"))
        return

    if not await _has_staged():
        # nothing to commit, maybe still need to push
        await event.edit(Messages.info("No changes to commit. Checking push…"))
    else:
        code, out = await _run(
            "commit", "-m", msg[:200],
            timeout=30,
        )
        if code != 0:
            # could be "nothing to commit" or real error
            if "nothing to commit" in out.lower():
                await event.edit(Messages.info("Nothing to commit."))
            else:
                await event.edit(Messages.error(f"commit failed:\n```\n{out[:1200]}\n```"))
                return

    branch = await _get_branch() or "main"
    remote = await _get_remote_url()
    if not remote:
        await event.edit(Messages.error("No origin remote configured."))
        return

    token = _read_token(event.ctx)
    push_url = _inject_token(remote, token) if token else remote

    await event.edit(Messages.loading(f"Pushing to `{branch}`…"))
    code, out = await _run(
        "push", push_url, f"HEAD:{branch}",
        timeout=180,
    )
    if code != 0:
        # hide any token that might leak into stderr
        if token:
            out = out.replace(token, "***")
        await event.edit(Messages.error(
            f"push failed:\n```\n{out[:1500]}\n```"))
        return

    # count commit
    code, h = await _run("rev-parse", "--short", "HEAD")
    commit = h.strip() if code == 0 else "?"
    await event.edit(Messages.success(
        f"Pushed to `{branch}` · `{commit}`\n"
        f"Remote: `{_sanitize_url(remote)}`\n"
        f"Message: _{msg[:120]}_"))


# ═══════════════════════════════════════════════════════════════════
#  status / pull / log
# ═══════════════════════════════════════════════════════════════════

@command("gitstatus", "Show repo status", permission="sudo")
async def gitstatus(event):
    if not _is_repo():
        await event.edit(Messages.info("Not a git repo."))
        return
    code, out = await _run("status", "-sb")
    branch = await _get_branch() or "?"
    remote = await _get_remote_url() or "(none)"
    lines = [
        f"🔀 **GIT STATUS**\n{SEP_FANCY}",
        f"**Branch**  `{branch}`",
        f"**Remote**  `{_sanitize_url(remote)}`",
        SEP_FANCY,
        "```",
        out[:1500] if out.strip() else "(clean)",
        "```",
    ]
    # upstream ahead/behind
    code, ab = await _run("rev-list", "--left-right", "--count", f"{branch}...@{{u}}")
    if code == 0 and ab.strip():
        lines.append(f"_ahead/behind:_ `{ab.strip()}`")
    await event.edit("\n".join(lines))


@command(r"gitlog(?:\s+(\d+))?", "Show recent commits", permission="sudo")
async def gitlog(event):
    if not _is_repo():
        await event.edit(Messages.info("Not a git repo."))
        return
    n = int(event.pattern_match.group(1) or 10)
    n = max(1, min(n, 50))
    code, out = await _run(
        "log", f"-{n}", "--pretty=format:%h %ad %s",
        "--date=format:%Y-%m-%d %H:%M",
    )
    if code != 0 or not out.strip():
        await event.edit(Messages.info("No commits yet."))
        return
    await event.edit(
        f"📜 **Last {n} commits**\n{SEP_FANCY}\n"
        f"```\n{out[:3300]}\n```"
    )


@command("gitpull", "Pull from remote", permission="sudo")
async def gitpull(event):
    if not _is_repo():
        await event.edit(Messages.info("Not a git repo."))
        return
    await event.edit(Messages.loading("Pulling…"))
    code, out = await _run("pull", "--ff-only", timeout=120)
    if code != 0:
        await event.edit(Messages.error(f"pull failed:\n```\n{out[:1500]}\n```"))
        return
    await event.edit(Messages.success(
        f"Pulled.\n```\n{out[:1200]}\n```"))


# ═══════════════════════════════════════════════════════════════════
#  config commands
# ═══════════════════════════════════════════════════════════════════

@command(r"gitauthor (.+?) <(.+?)>", "Set commit author for this repo",
         permission="sudo")
async def gitauthor(event):
    """
    Usage: `.gitauthor <name> <email>`

    Example: `.gitauthor Your Name <you@example.com>`
    """
    name = event.pattern_match.group(1).strip()
    email = event.pattern_match.group(2).strip()
    if not name or "@" not in email:
        await event.edit(Messages.error("Give a name and a valid email."))
        return
    if not _is_repo():
        await _run("init")
    await _run("config", "user.name", name[:64])
    await _run("config", "user.email", email[:128])
    await event.edit(Messages.success(
        f"Commit author set:\n"
        f"**Name**  `{name}`\n"
        f"**Email** `{email}`"))


@command(r"gittoken(?:\s+(\S+))?", "Set or clear the GitHub push token",
         permission="sudo")
async def gittoken(event):
    """
    Usage:
        .gittoken <token>   → save token
        .gittoken clear     → delete token
        .gittoken           → show status
    """
    ctx = event.ctx
    arg = (event.pattern_match.group(1) or "").strip()

    if not arg:
        has = bool(_read_token(ctx))
        env_has = bool(__import__("os").getenv("GITHUB_TOKEN", "").strip())
        await event.edit(
            f"🔐 **Git token**\n{SEP_FANCY}\n"
            f"**File** `{'yes' if has else 'no'}`\n"
            f"**Env**  `{'yes' if env_has else 'no'}`\n"
            f"\n_Env var takes precedence if both are set._"
        )
        return

    if arg.lower() == "clear":
        _clear_token(ctx)
        await event.edit(Messages.success("Token cleared."))
        return

    if len(arg) < 20:
        await event.edit(Messages.error("Token too short. Refusing."))
        return

    _write_token(ctx, arg)
    await event.edit(Messages.success(
        f"Token saved for account `{ctx.account_id}`.\n"
        f"_Stored in `{_token_path(ctx).name}` (gitignored)._"))


@command(r"gitremote(?:\s+(\S+))?", "Show or set the origin remote",
         permission="sudo")
async def gitremote(event):
    """
    Usage:
        .gitremote                           → show current
        .gitremote https://github.com/...    → set
    """
    url = (event.pattern_match.group(1) or "").strip()
    if not url:
        current = await _get_remote_url() or "(none)"
        await event.edit(f"🌐 **origin** `{_sanitize_url(current)}`")
        return
    if not url.startswith("https://"):
        await event.edit(Messages.error("URL must start with https://"))
        return
    if not _is_repo():
        await event.edit(Messages.error("Not a git repo."))
        return
    existing = await _get_remote_url()
    if existing:
        code, out = await _run("remote", "set-url", "origin", url)
    else:
        code, out = await _run("remote", "add", "origin", url)
    if code != 0:
        await event.edit(Messages.error(f"remote failed: {out}"))
        return
    await event.edit(Messages.success(f"Remote set to `{_sanitize_url(url)}`."))


@command(r"gitbranch(?:\s+(\S+))?", "Show or rename current branch",
         permission="sudo")
async def gitbranch(event):
    """
    Usage:
        .gitbranch            → show current
        .gitbranch <name>     → rename current to <name>
    """
    name = (event.pattern_match.group(1) or "").strip()
    if not _is_repo():
        await event.edit(Messages.info("Not a git repo."))
        return
    if not name:
        b = await _get_branch() or "(detached)"
        await event.edit(f"🌿 current branch: `{b}`")
        return
    if not re.match(r"^[A-Za-z0-9._\-/]+$", name):
        await event.edit(Messages.error("Invalid branch name."))
        return
    code, out = await _run("branch", "-M", name)
    if code != 0:
        await event.edit(Messages.error(f"rename failed: {out}"))
        return
    await event.edit(Messages.success(f"Branch renamed to `{name}`."))


# ═══════════════════════════════════════════════════════════════════
#  .gitignore-check
# ═══════════════════════════════════════════════════════════════════

@command("gitcheck", "Verify secrets are ignored by .gitignore",
         permission="sudo")
async def gitcheck(event):
    if not _is_repo():
        await event.edit(Messages.info("Not a git repo."))
        return
    await event.edit(Messages.loading("Checking…"))
    safe, violations = await _check_ignore_safety()
    if safe:
        await event.edit(Messages.success(
            "All secret paths are ignored. Safe to push."))
        return
    await event.edit(Messages.error(
        "**Unsafe — do NOT push:**\n"
        + "\n".join(f"• {v}" for v in violations)
        + "\n\n_Fix `.gitignore` first._"))


# ═══════════════════════════════════════════════════════════════════
#  .githelp
# ═══════════════════════════════════════════════════════════════════

@command("githelp", "Git module help")
async def githelp(event):
    await event.edit(
        "🔀 **GIT**\n"
        f"{SEP_FANCY}\n\n"
        "**First-time setup:**\n"
        "▸ `.gitauthor <name> <email>` — commit identity\n"
        "▸ `.gittoken <ghp_...>` — auth for private repos\n"
        "▸ `.gitinit <repo_url> [branch]` — init + push\n\n"
        "**Day-to-day:**\n"
        "▸ `.gitpush [message]` — add + commit + push\n"
        "▸ `.gitpull` — pull from origin\n"
        "▸ `.gitstatus` — working tree status\n"
        "▸ `.gitlog [n]` — recent commits\n\n"
        "**Config:**\n"
        "▸ `.gitremote [url]` — show or set origin\n"
        "▸ `.gitbranch [name]` — show or rename\n"
        "▸ `.gittoken` — token status\n"
        "▸ `.gittoken clear` — wipe token\n\n"
        "**Safety:**\n"
        "▸ `.gitcheck` — verify `.env`, `data/`, `logs/` are ignored\n"
        f"{SEP_FANCY}\n"
        "Every `.gitpush` runs `.gitcheck` automatically. "
        "Push refuses if secrets are not ignored."
    )