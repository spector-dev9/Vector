from datetime import datetime


class Formatters:
    @staticmethod
    def format_size(num):
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if num < 1024.0:
                return f"{num:.2f} {unit}"
            num /= 1024.0
        return f"{num:.2f} PB"

    @staticmethod
    def format_duration(seconds):
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        if seconds < 60:
            return f"{seconds:.1f}s"
        if seconds < 3600:
            return f"{int(seconds//60)}m {int(seconds%60)}s"
        return f"{int(seconds//3600)}h {int((seconds%3600)//60)}m"

    @staticmethod
    def format_uptime(started_at):
        delta = datetime.now() - started_at
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts)

    @staticmethod
    def truncate(text, length=100, suffix="..."):
        return text if len(text) <= length else text[:length - len(suffix)] + suffix
