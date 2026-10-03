from core.logger import setup_logger

logger = setup_logger("VECTOR.messages")


async def resolve_target(client, event, arg=None):
    if arg:
        from .users import resolve_user
        u = await resolve_user(client, arg)
        if u:
            return u
    if getattr(event, "is_reply", False):
        try:
            replied = await event.get_reply_message()
            if replied:
                sender = await replied.get_sender()
                if sender and hasattr(sender, "id"):
                    return sender
        except Exception:
            pass
    return None


async def safe_edit(event, text, fallback_reply=True):
    try:
        await event.edit(text)
        return "edited"
    except Exception:
        if fallback_reply:
            try:
                await event.reply(text)
                return "replied"
            except Exception:
                return "failed"
        return "failed"


async def safe_delete(event):
    try:
        await event.delete()
    except Exception:
        pass
