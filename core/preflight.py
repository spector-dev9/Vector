"""Pre-flight checks that run before any account is initialized.

Fails fast so a broken tree never half-starts.
"""
from __future__ import annotations
from pathlib import Path

from core.logger import setup_logger

logger = setup_logger("VECTOR.preflight")


def _check_writable(label: str, path: Path, problems: list) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except Exception as e:
        problems.append(f"{label} dir not writable: {path} ({e})")


def run_preflight(registry, config) -> tuple:
    """Return (ok: bool, problems: list[str])."""
    problems: list = []

    _check_writable("logs", Path(config.LOGS_DIR), problems)
    _check_writable("accounts", Path(config.ACCOUNTS_DIR), problems)
    _check_writable("data", Path(config.DATA_DIR), problems)

    seen: dict = {}
    for name, meta in registry.commands.items():
        owner = meta.get("module", "?")
        if name in seen and seen[name] != owner:
            problems.append(
                f"command '{name}' registered twice: {seen[name]} vs {owner}"
            )
        seen[name] = owner

    for key, info in registry.modules.items():
        if not Path(info.path).exists():
            problems.append(f"module {key}: file missing at {info.path}")

    return (not problems, problems)
