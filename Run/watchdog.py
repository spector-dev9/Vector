"""Per-account reconnect watchdog."""
import asyncio
from core.logger import setup_logger

logger = setup_logger("VECTOR.watchdog")


class Watchdog:
    def __init__(self, runtime, interval: int = 90):
        self.runtime = runtime
        self.interval = interval
        self.running = False
        self._consecutive_failures = 0

    async def start(self):
        self.running = True
        while self.running:
            try:
                await asyncio.sleep(self.interval)
                if not self.running:
                    break
                await self._check()
            except asyncio.CancelledError:
                break

    def stop(self):
        self.running = False

    async def _check(self):
        try:
            if await self.runtime.health.check():
                self._consecutive_failures = 0
                return
            logger.warning(
                f"{self.runtime.ctx.log_tag} health check failed; recovering…"
            )
            ok = await self.runtime.recovery.recover()
            if ok:
                self._consecutive_failures = 0
                logger.info(f"{self.runtime.ctx.log_tag} recovery succeeded")
                return
            raise RuntimeError("recovery failed")
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(
                f"{self.runtime.ctx.log_tag} watchdog (attempt "
                f"{self._consecutive_failures}): {e}",
                exc_info=True,
            )
            if self._consecutive_failures >= 5:
                logger.critical(
                    f"{self.runtime.ctx.log_tag} account unhealthy — "
                    f"stopping watchdog"
                )
                self.running = False
