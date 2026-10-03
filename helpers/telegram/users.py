from core.logger import setup_logger

logger = setup_logger("VECTOR.users")


async def resolve_user(client, arg):
    arg = (arg or "").strip()
    if not arg:
        return None
    try:
        if arg.startswith("@"):
            return await client.get_entity(arg)
        if arg.lstrip("-").isdigit():
            return await client.get_entity(int(arg))
        return await client.get_entity(arg)
    except Exception as e:
        logger.debug(f"resolve_user '{arg}': {e}")
        return None


async def warm_user_cache(client, user_id):
    try:
        await client.get_entity(user_id)
    except Exception:
        pass
    try:
        from telethon import functions
        await client(functions.users.GetFullUserRequest(id=user_id))
    except Exception:
        pass
