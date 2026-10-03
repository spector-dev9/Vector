from telethon.tl.types import Channel, Chat, User


def chat_kind(e):
    if isinstance(e, User):
        return "bot" if getattr(e, "bot", False) else "user"
    if isinstance(e, Chat):
        return "group"
    if isinstance(e, Channel):
        return "channel" if getattr(e, "broadcast", False) else "supergroup"
    return "unknown"


async def resolve_chat(client, raw):
    try:
        n = int(raw)
    except ValueError:
        try:
            return await client.get_entity(raw)
        except Exception:
            return None
    s = str(n)
    candidates = [n]
    if s.startswith("-100"):
        candidates += [int(s[4:]), -int(s[4:])]
    elif s.startswith("-"):
        candidates += [int(s[1:]), int("-100" + s[1:])]
    else:
        candidates += [int("-100" + s), -n]
    for cid in candidates:
        try:
            return await client.get_entity(cid)
        except Exception:
            continue
    return None
