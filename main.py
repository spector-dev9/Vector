#!/usr/bin/env python3
"""V E C T O R — multi-account Telegram userbot."""
import asyncio
import sys

from Config.settings import Config
from core.logger import setup_logger
from core.manager import VectorManager
from core.preflight import run_preflight
from Run.runtime import Runtime
from Run.shutdown import ShutdownHandler

logger = setup_logger("VECTOR.main")

BANNER = """
    ╔══════════════════════════════════════╗
    ║     V  E  C  T  O  R                  ║
    ║     multi-account telegram userbot    ║
    ╚══════════════════════════════════════╝
"""


async def main():
    print(BANNER)
    Config.validate()
    logger.info(f"📋 accounts: {', '.join(Config.ACCOUNTS)}")

    manager = VectorManager()
    mods, handlers = manager.load_plugins()
    logger.info(f"🔌 loaded {mods} module(s) · {handlers} handler(s)")

    ok, problems = run_preflight(manager.registry, Config)
    if not ok:
        logger.critical("❌ pre-flight failed:")
        for p in problems:
            logger.critical(f"   - {p}")
        sys.exit(1)
    logger.info("✅ pre-flight ok")

    runtimes = []
    for account_id in Config.ACCOUNTS:
        rt = Runtime(account_id, manager)
        try:
            await rt.initialize()
        except Exception as e:
            logger.error(f"[{account_id}] init failed: {e}", exc_info=True)
            try:
                await rt.db.dispose()
            except Exception:
                pass
            continue
        await manager.attach_account(rt.ctx)
        runtimes.append(rt)

    if not runtimes:
        logger.critical("no accounts started — exiting")
        sys.exit(1)

    for rt in runtimes:
        await rt.start()

    ShutdownHandler(manager).setup()

    try:
        await asyncio.gather(
            *[rt.client.client.run_until_disconnected() for rt in runtimes]
        )
    except KeyboardInterrupt:
        logger.info("⏹ interrupted")
    finally:
        for rt in runtimes:
            await rt.stop()
        logger.info("👋 goodnight")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
