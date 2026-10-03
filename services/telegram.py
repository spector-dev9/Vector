from telethon import functions


class TelegramService:
    def __init__(self, client):
        self.client = client

    async def full_user(self, user_id):
        return await self.client(functions.users.GetFullUserRequest(id=user_id))

    async def full_channel(self, entity):
        return await self.client(functions.channels.GetFullChannelRequest(channel=entity))

    async def common_chats(self, user_id):
        try:
            r = await self.full_user(user_id)
            return getattr(r.full_user, "common_chats_count", 0) or 0
        except Exception:
            return 0
