"""Per-account bot state."""
from datetime import datetime


class BotState:
    def __init__(self):
        self.started_at = datetime.now()
        self.status = "initializing"
        self.command_count = 0
        self.error_count = 0

    def start(self):
        self.started_at = datetime.now()
        self.status = "running"

    def stop(self):
        self.status = "stopped"

    def increment_commands(self):
        self.command_count += 1

    def increment_errors(self):
        self.error_count += 1

    def uptime_seconds(self):
        return (datetime.now() - self.started_at).total_seconds()

    def get_stats(self):
        return {
            "status": self.status,
            "uptime": self.uptime_seconds(),
            "commands": self.command_count,
            "errors": self.error_count,
            "started_at": self.started_at.isoformat(),
        }
