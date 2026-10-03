"""Basic health checks."""
from core.logger import setup_logger

logger = setup_logger("VECTOR.health")


class HealthMonitor:
    def __init__(self, runtime):
        self.runtime = runtime
        self.status = "healthy"

    async def check(self) -> bool:
        try:
            if not self.runtime.client.client.is_connected():
                self.status = "disconnected"
                return False
            if self.runtime.state.status != "running":
                self.status = "not_running"
                return False
            self.status = "healthy"
            return True
        except Exception as e:
            logger.error(f"{self.runtime.ctx.log_tag} health: {e}")
            self.status = "error"
            return False
