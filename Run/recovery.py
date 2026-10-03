"""Account-local recovery."""
from core.logger import setup_logger

logger = setup_logger("VECTOR.recovery")


class Recovery:
    def __init__(self, runtime):
        self.runtime = runtime

    async def recover(self) -> bool:
        try:
            await self.runtime.client.client.connect()
            return True
        except Exception as e:
            logger.error(f"{self.runtime.ctx.log_tag} recovery: {e}")
            return False
