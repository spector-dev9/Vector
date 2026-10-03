""".uname / .bio / .name."""
from telethon import functions
from core.decorators import command
from core.module import ModuleMeta
from utils import Messages

META = ModuleMeta(
    name="account", category="root",
    description="Direct edits to profile name, bio, username.",
    permission="user",
)


@command(r"uname(?: (.+))?", "Get or set username")
async def uname(event):
    arg = event.pattern_match.group(1)
    if not arg:
        me = await event.client.get_me()
        await event.edit(f"username: @{me.username or '—'}")
        return
    arg = arg.strip().lstrip("@")
    try:
        await event.client(functions.account.UpdateUsernameRequest(username=arg))
        await event.edit(Messages.success(f"username → @{arg}"))
    except Exception as e:
        await event.edit(Messages.error(str(e)))


@command(r"bio(?: (.+))?", "Get or set bio")
async def bio(event):
    arg = event.pattern_match.group(1)
    if not arg:
        me = await event.client.get_me()
        full = await event.client(functions.users.GetFullUserRequest(id=me.id))
        await event.edit(f"bio: {full.full_user.about or '—'}")
        return
    try:
        await event.client(functions.account.UpdateProfileRequest(about=arg[:70]))
        await event.edit(Messages.success("bio updated."))
    except Exception as e:
        await event.edit(Messages.error(str(e)))


@command(r"name(?: (.+?)(?:\s*\|\s*(.+))?)?", "Get or set first|last name")
async def name(event):
    first = event.pattern_match.group(1)
    last = event.pattern_match.group(2)
    if not first:
        me = await event.client.get_me()
        await event.edit(f"name: {me.first_name} {me.last_name or ''}")
        return
    try:
        await event.client(functions.account.UpdateProfileRequest(
            first_name=first[:64], last_name=(last or "")[:64],
        ))
        await event.edit(Messages.success("name updated."))
    except Exception as e:
        await event.edit(Messages.error(str(e)))
