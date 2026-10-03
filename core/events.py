from telethon import events


def new_message(**kw):
    return events.NewMessage(**kw)


def outgoing(pattern):
    return events.NewMessage(pattern=pattern, outgoing=True)


def incoming(**kw):
    return events.NewMessage(incoming=True, **kw)


def user_update():
    return events.UserUpdate()
