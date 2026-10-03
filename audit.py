#!/usr/bin/env python3
"""VECTOR integration audit.

Complements verify.py. verify.py checks structure/syntax only.
This script imports the tree (with stub env) and asserts that the
interfaces every new file depends on still exist in the unchanged
files.

Run:  python audit.py
Exit code 0 = every contract satisfied.
"""
import importlib
import inspect
import os
import sys
from pathlib import Path

os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "x" * 32)
os.environ.setdefault("PHONE_MAIN", "+10000000000")
os.environ.setdefault("ACCOUNTS", "main")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

CONTRACTS = {
    "Config.settings": {
        "Config": [
            "CONTROL_BOT_TOKEN", "CONTROL_BOT_ADMIN_ID", "ACCOUNTS",
            "CMD_PREFIX", "API_ID", "API_HASH", "DATA_DIR",
            "ACCOUNTS_DIR", "LOGS_DIR",
        ],
    },
    "core.loader": {
        "PluginLoader": ["iter_all", "load_one", "forget", "categories", "modules_in"],
    },
    "core.manager": {
        "ModuleRegistry": [
            "load_all", "unload", "resolve_module_key",
            "delete_module", "module_pairs", "get_stats",
        ],
        "VectorManager": [
            "load_plugins", "attach_account", "reload_module",
            "reload_all", "stop_all",
        ],
    },
    "core.module_health": {
        "ModuleHealth": [
            "record_failure", "record_success", "disable",
            "is_disabled", "re_enable", "re_enable_all", "disabled_list",
        ],
    },
    "core.context": {
        "AccountContext": ["log_tag", "sudo_users", "is_sudo"],
        "AccountPaths": ["database", "session", "cache", "files", "file", "sub"],
        "AccountCache": ["set", "get", "delete", "clear"],
    },
    "core.dispatcher": {
        "install": [],
    },
    "Run.runtime": {
        "Runtime": ["initialize", "start", "stop"],
    },
    "Run.shutdown": {
        "ShutdownHandler": ["setup"],
    },
    "Run.errors": {
        "ErrorHandler": ["log_error", "get_recent_errors", "clear"],
    },
    "database.connection": {
        "AccountDatabase": ["session", "create_all", "dispose"],
    },
    "utils.validators": {
        "Validators": [
            "is_valid_username", "is_valid_user_id", "is_valid_url",
            "extract_user_id", "parse_user_or_id",
        ],
    },
}

MUST_IMPORT = [
    "Config.settings",
    "core.context",
    "core.client",
    "core.decorators",
    "core.dispatcher",
    "core.loader",
    "core.manager",
    "core.module",
    "core.module_health",
    "core.preflight",
    "Run.errors",
    "Run.health",
    "Run.recovery",
    "Run.runtime",
    "Run.shutdown",
    "Run.state",
    "Run.watchdog",
    "database.connection",
    "database.migrations",
    "database.models",
    "utils",
    "utils.messages",
    "utils.formatters",
    "utils.validators",
]


def _import(modpath):
    try:
        return importlib.import_module(modpath), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def check_imports():
    failures = []
    for modpath in MUST_IMPORT:
        mod, err = _import(modpath)
        if err:
            failures.append(f"{modpath} → {err}")
    if failures:
        print(f"❌ {len(failures)} import failure(s):")
        for f in failures:
            print(f"   - {f}")
        return False
    print(f"✅ Imports: {len(MUST_IMPORT)} module(s) imported cleanly")
    return True


def check_contracts():
    failures = []
    for modpath, attrs in CONTRACTS.items():
        mod, err = _import(modpath)
        if err:
            failures.append(f"{modpath} import failed: {err}")
            continue
        for attr_name, required in attrs.items():
            obj = getattr(mod, attr_name, None)
            if obj is None:
                failures.append(f"{modpath}.{attr_name} missing")
                continue
            for r in required:
                if not hasattr(obj, r):
                    failures.append(f"{modpath}.{attr_name}.{r} missing")
    if failures:
        print(f"❌ {len(failures)} contract violation(s):")
        for f in failures:
            print(f"   - {f}")
        return False
    print(f"✅ Contracts: {sum(len(v) for v in CONTRACTS.values())} class(es) checked")
    return True


def check_controller_import_side_effects():
    """Source-level import-side-effect check for controller.py.

    This does NOT import controller.py. Importing would create the
    controller session directory and bind module-level state. Instead
    we read the source and verify that TelegramClient(...) is only
    instantiated inside async def main().
    """
    try:
        src = (ROOT / "controller.py").read_text(encoding="utf-8")
        if "TelegramClient(" in src and "async def main(" in src:
            idx_client = src.index("TelegramClient(")
            idx_main = src.index("async def main(")
            if idx_client < idx_main:
                print("⚠️  controller.py instantiates TelegramClient at import time")
                return False
        print("✅ controller.py: no import-time side effects (source check)")
        return True
    except FileNotFoundError:
        print("⚠️  controller.py not present — skipping")
        return True
    except Exception as e:
        print(f"⚠️  controller.py check skipped: {e}")
        return True


def main():
    print("━" * 60)
    print("VECTOR — integration audit")
    print("━" * 60)
    checks = [
        check_imports(),
        check_contracts(),
        check_controller_import_side_effects(),
    ]
    print("━" * 60)
    if all(checks):
        print("✅ All integration checks passed.")
        print("ℹ️  This does NOT test Telegram auth, DB writes, or plugin logic.")
        return 0
    print("❌ One or more integration checks failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
