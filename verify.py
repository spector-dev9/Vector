#!/usr/bin/env python3
"""VECTOR offline verifier — no Telegram / no DB required.

Run before every start:  python verify.py
Exit code 0 = all checks pass.
"""
import ast
import compileall
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED = [
    "main.py", "requirements.txt", ".env.example",
    "Config/settings.py", "Config/environment.py",
    "core/client.py", "core/context.py", "core/decorators.py",
    "core/loader.py", "core/manager.py", "core/module.py",
    "core/dispatcher.py", "core/module_health.py", "core/preflight.py",
    "Run/runtime.py", "Run/state.py", "Run/health.py",
    "Run/watchdog.py", "Run/recovery.py", "Run/shutdown.py", "Run/errors.py",
    "database/connection.py", "database/models.py", "database/migrations.py",
    "helpers/network/http.py", "helpers/telegram/admins.py",
    "helpers/telegram/messages.py", "helpers/formatting/animator.py",
    "utils/validators.py",
    "plugins/system/help.py", "plugins/sudo/control.py",
    "plugins/sudo/health.py", "plugins/account/save.py",
    "plugins/developer/errors.py",
]

PLUGIN_DIRS = [
    "root", "sudo", "account", "telegram", "moderation",
    "automation", "media", "tools", "developer", "fun", "system",
]


def check_structure():
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    if missing:
        print("❌ Missing required files:")
        for p in missing:
            print(f"   - {p}")
        return False
    print(f"✅ Structure: {len(REQUIRED)} required files present")
    return True


def check_compile():
    ok = compileall.compile_dir(
        str(ROOT), quiet=1, maxlevels=20,
        rx=re.compile(r"(^|[\\/])(\.git|venv|env|\.venv|__pycache__|data)([\\/]|$)"),
    )
    if not ok:
        print("❌ Python compilation failed")
        return False
    print("✅ Python syntax: all modules compile")
    return True


def check_plugin_categories():
    missing = [c for c in PLUGIN_DIRS if not (ROOT / "plugins" / c).is_dir()]
    if missing:
        print(f"⚠️  Missing plugin categories: {', '.join(missing)}")
    else:
        print(f"✅ Plugin categories: {len(PLUGIN_DIRS)} present")
    return True


def check_decorators():
    plugins_root = ROOT / "plugins"
    if not plugins_root.exists():
        print("⚠️  No plugins/ dir — skipping")
        return True
    commands = listeners = files = 0
    for path in plugins_root.rglob("*.py"):
        if path.name.startswith("_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ AST parse failed for {path}: {e}")
            return False
        files += 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call):
                        name = getattr(dec.func, "id", "")
                        if name == "command":
                            commands += 1
                        elif name == "listener":
                            listeners += 1
    print(f"✅ Plugins: {files} file(s) · {commands} command(s) · {listeners} listener(s)")
    return True


def check_account_isolation_patterns():
    """Flag module-level mutable state that isn't account-keyed."""
    warnings = []
    plugins_root = ROOT / "plugins"
    if not plugins_root.exists():
        return True
    for path in plugins_root.rglob("*.py"):
        try:
            src = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in re.finditer(
            r"^_?(state|cache|sniped|duels|trivia|active|batch|reply_ids|"
            r"last_run|cooldown|spam)\s*[:=]\s*(\{|dict\()",
            src, re.MULTILINE,
        ):
            warnings.append(f"{path.relative_to(ROOT)}: `{m.group(1)}`")
    if warnings:
        print(f"⚠️  Potential cross-account state ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"   - {w}")
    else:
        print("✅ No obvious module-level account-unsafe state")
    return True


def main():
    print("━" * 60)
    print("VECTOR — offline verifier")
    print("━" * 60)
    checks = [
        check_structure(),
        check_compile(),
        check_plugin_categories(),
        check_decorators(),
        check_account_isolation_patterns(),
    ]
    print("━" * 60)
    if all(checks):
        print("✅ All checks passed. Live Telegram/DB was NOT tested.")
        return 0
    print("❌ One or more checks failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
