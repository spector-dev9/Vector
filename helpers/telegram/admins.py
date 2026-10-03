"""Admin checks + user/reason resolution."""
from __future__ import annotations

from telethon.tl.types import (
    ChannelParticipantAdmin, ChannelParticipantCreator,
    MessageEntityMentionName, User,
)
from core.logger import setup_logger

logger = setup_logger("VECTOR.admins")


async def is_admin(client, chat_id: int, user_id: int) -> bool:
    if not str(chat_id).startswith("-100"):
        return False
    try:
        perms = await client.get_permissions(chat_id, user_id)
        return isinstance(
            perms.participant,
            (ChannelParticipantAdmin, ChannelParticipantCreator),
        )
    except Exception as e:
        logger.debug(f"is_admin: {e}")
        return False


async def get_user_and_reason(event, group: int = 1):
    try:
        arg = event.pattern_match.group(group)
    except (IndexError, AttributeError):
        arg = None
    extra = None
    reply = await event.get_reply_message()

    if arg:
        if event.message.entities:
            for ent in event.message.entities:
                if isinstance(ent, MessageEntityMentionName):
                    try:
                        u = await event.client.get_entity(ent.user_id)
                        rest = (event.raw_text or "")[ent.offset + ent.length:].strip()
                        return u, rest or None
                    except Exception:
                        pass
        parts = arg.split(maxsplit=1)
        target = parts[0]
        if len(parts) > 1:
            extra = parts[1]
        try:
            if target.lstrip("-").isdigit():
                return await event.client.get_entity(int(target)), extra
            if target.startswith("@"):
                return await event.client.get_entity(target), extra
        except Exception as e:
            logger.debug(f"resolve '{target}': {e}")

    if event.is_private:
        try:
            return await event.get_chat(), extra or arg
        except Exception:
            return None, None

    if reply:
        try:
            sender = await reply.get_sender()
            if isinstance(sender, User):
                return sender, extra or arg
        except Exception:
            pass

    return None, None


async def mention(user) -> str:
    if user is None:
        return "unknown"
    if getattr(user, "username", None):
        return f"@{user.username}"
    name = getattr(user, "first_name", None) or str(getattr(user, "id", "?"))
    return f"[{name}](tg://user?id={user.id})"
