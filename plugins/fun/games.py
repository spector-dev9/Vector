"""Games — dice, RPS, duels, trivia. Account-scoped."""
import asyncio
import random

from telethon import Button, events
from telethon.tl.types import InputMediaDice
from sqlalchemy import select

from core.decorators import command, listener
from core.module import ModuleMeta
from database.models import GameStat
from utils import Messages

META = ModuleMeta(
    name="games", category="fun",
    description="Dice, RPS, duels, trivia, stats.",
    permission="user",
)

_RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
_RPS_EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}

_8BALL = [
    "It is certain.", "Without a doubt.", "Yes, definitely.",
    "You may rely on it.", "As I see it, yes.", "Most likely.",
    "Outlook good.", "Yes.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.",
    "Better not tell you now.", "Cannot predict now.",
    "Concentrate and ask again.", "Don't count on it.",
    "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful.",
]

_TRIVIA = [
    {"q": "Capital of France?", "o": ["Paris", "London", "Berlin", "Madrid"], "a": 0},
    {"q": "Largest planet?", "o": ["Earth", "Mars", "Jupiter", "Saturn"], "a": 2},
    {"q": "WW2 ended in?", "o": ["1943", "1944", "1945", "1946"], "a": 2},
    {"q": "Symbol for gold?", "o": ["Go", "Gd", "Au", "Ag"], "a": 2},
    {"q": "Bits in a byte?", "o": ["4", "8", "16", "32"], "a": 1},
]

_LETTERS = ["A", "B", "C", "D"]
_duels = {}
_trivia = {}


async def _bump(ctx, uid, field, amount=1):
    async with ctx.database.session() as s:
        r = await s.execute(select(GameStat).where(GameStat.user_id == uid))
        row = r.scalar_one_or_none()
        if row is None:
            row = GameStat(user_id=uid)
            s.add(row)
        setattr(row, field, (getattr(row, field, 0) or 0) + amount)


async def _dice(client, chat_id, emoji):
    try:
        sent = await client.send_message(chat_id, file=InputMediaDice(emoji))
        await asyncio.sleep(2)
        result = await client.get_messages(chat_id, ids=sent.id)
        return getattr(result.media, "value", None)
    except Exception:
        return None


@command("dice", "Roll dice")
async def dice(e):
    await e.delete()
    if await _dice(e.client, e.chat_id, "🎲") is not None:
        await _bump(e.ctx, e.sender_id, "dice_played")


@command("dart", "Dart")
async def dart(e):
    await e.delete()
    await _dice(e.client, e.chat_id, "🎯")


@command("bowl", "Bowling")
async def bowl(e):
    await e.delete()
    await _dice(e.client, e.chat_id, "🎳")


@command("basket", "Basketball")
async def basket(e):
    await e.delete()
    await _dice(e.client, e.chat_id, "🏀")


@command("football", "Football")
async def football(e):
    await e.delete()
    await _dice(e.client, e.chat_id, "⚽")


@command("slot", "Slots")
async def slot(e):
    await e.delete()
    v = await _dice(e.client, e.chat_id, "🎰")
    if v is None:
        return
    await _bump(e.ctx, e.sender_id, "slots_played")
    if v == 64:
        await _bump(e.ctx, e.sender_id, "jackpots")
        await e.client.send_message(e.chat_id, "🎉 **JACKPOT!**")


@command(r"8ball (.+)", "Magic 8-ball")
async def eightball(e):
    await e.edit(f"🎱 **Q:** {e.pattern_match.group(1)}\n**A:** _{random.choice(_8BALL)}_")


@command("coinflip", "Coinflip")
async def coinflip(e):
    await e.edit(f"🪙 **{random.choice(['Heads', 'Tails'])}**")


@command(r"rps (rock|paper|scissors)", "Rock-paper-scissors")
async def rps(e):
    u = e.pattern_match.group(1).lower()
    b = random.choice(list(_RPS_BEATS))
    result = ("🤝 Tie!" if u == b
              else ("🎉 You win!" if _RPS_BEATS[u] == b else "🤖 Bot wins!"))
    await e.edit(f"**You:** {_RPS_EMOJI[u]} {u}\n**Bot:** {_RPS_EMOJI[b]} {b}\n\n{result}")


@command("duel", "Duel replied user")
async def duel(e):
    if not e.is_reply:
        await e.edit(Messages.error("Reply to someone."))
        return
    replied = await e.get_reply_message()
    opp = await replied.get_sender()
    if not opp or opp.id == e.sender_id or getattr(opp, "bot", False):
        await e.edit(Messages.error("Invalid opponent."))
        return
    me = await e.get_sender()
    cn = getattr(me, "first_name", None) or "You"
    on = getattr(opp, "first_name", None) or str(opp.id)
    msg = await e.respond(
        f"⚔️ **DUEL** — **{cn}** vs **{on}**",
        buttons=[[
            Button.inline("⚔️ Accept", data=f"duel:accept:{e.sender_id}:{opp.id}"),
            Button.inline("❌ Decline", data=f"duel:decline:{e.sender_id}:{opp.id}"),
        ]],
    )
    _duels[(e.ctx.account_id, msg.id)] = {
        "challenger": e.sender_id, "opponent": opp.id, "cn": cn, "on": on,
    }
    await e.delete()


@listener(events.CallbackQuery())
async def duel_cb(e):
    try:
        data = e.data.decode()
    except Exception:
        return
    if not data.startswith("duel:"):
        return
    parts = data.split(":")
    if len(parts) != 4:
        return
    _, action, ch, op = parts
    ch, op = int(ch), int(op)
    ctx = getattr(e.client, "ctx", None)
    if ctx is None:
        return
    d = _duels.get((ctx.account_id, e.message_id))
    if not d:
        await e.answer("Expired.", alert=True)
        return
    if e.sender_id != op:
        await e.answer("Not for you.", alert=True)
        return
    if action == "decline":
        _duels.pop((ctx.account_id, e.message_id), None)
        await e.edit(f"❌ **{d['on']}** declined.")
        return
    a = random.choice(list(_RPS_BEATS))
    b = random.choice(list(_RPS_BEATS))
    if a == b:
        result, winner = "🤝 Tie!", None
    elif _RPS_BEATS[a] == b:
        result, winner = f"🏆 **{d['cn']}** wins!", ch
    else:
        result, winner = f"🏆 **{d['on']}** wins!", op
    _duels.pop((ctx.account_id, e.message_id), None)
    await e.edit(
        f"⚔️ **DUEL**\n**{d['cn']}:** {_RPS_EMOJI[a]} {a}\n"
        f"**{d['on']}:** {_RPS_EMOJI[b]} {b}\n\n{result}"
    )
    if winner:
        loser = op if winner == ch else ch
        await _bump(ctx, winner, "duels_won")
        await _bump(ctx, loser, "duels_lost")


@command("trivia", "Trivia question")
async def trivia(e):
    q = random.choice(_TRIVIA)
    opts = list(enumerate(q["o"]))
    random.shuffle(opts)
    shuffled = [t for _, t in opts]
    correct = next(i for i, (orig, _) in enumerate(opts) if orig == q["a"])
    body = f"🧠 **TRIVIA**\n\n{q['q']}\n"
    for i, t in enumerate(shuffled):
        body += f"\n**{_LETTERS[i]}.** {t}"
    msg = await e.respond(body)
    btns = [[Button.inline(_LETTERS[i], data=f"triv:{msg.id}:{i}")
             for i in range(len(shuffled))]]
    await msg.edit(body, buttons=btns)
    _trivia[(e.ctx.account_id, msg.id)] = {"correct": correct}
    await e.delete()


@listener(events.CallbackQuery())
async def trivia_cb(e):
    try:
        data = e.data.decode()
    except Exception:
        return
    if not data.startswith("triv:"):
        return
    parts = data.split(":")
    if len(parts) != 3:
        return
    try:
        chosen = int(parts[2])
    except ValueError:
        await e.answer()
        return
    ctx = getattr(e.client, "ctx", None)
    if ctx is None:
        return
    st = _trivia.get((ctx.account_id, e.message_id))
    if not st:
        await e.answer("Expired.", alert=True)
        return
    if chosen == st["correct"]:
        _trivia.pop((ctx.account_id, e.message_id), None)
        await _bump(ctx, e.sender_id, "trivia_won")
        try:
            u = await e.client.get_entity(e.sender_id)
            name = u.first_name or str(e.sender_id)
        except Exception:
            name = str(e.sender_id)
        await e.edit(f"🎉 **{name}** answered correctly!")
    else:
        await _bump(ctx, e.sender_id, "trivia_lost")
        await e.answer("❌ Wrong", alert=True)


@command(r"gstats(?:\s+(.+))?", "Game stats")
async def gstats(e):
    arg = (e.pattern_match.group(1) or "").strip()
    try:
        if arg:
            entity = await e.client.get_entity(
                int(arg) if arg.lstrip("-").isdigit() else arg)
        elif e.is_reply:
            entity = await (await e.get_reply_message()).get_sender()
        else:
            entity = await e.client.get_me()
    except Exception:
        await e.edit(Messages.error("Could not resolve."))
        return
    async with e.ctx.database.session() as s:
        r = await s.execute(select(GameStat).where(GameStat.user_id == entity.id))
        row = r.scalar_one_or_none()
    name = getattr(entity, "first_name", None) or str(entity.id)
    if row is None:
        await e.edit(Messages.info(f"No stats for **{name}**."))
        return
    await e.edit(
        f"🎮 **{name}**\n\n🎲 Dice: **{row.dice_played}**\n"
        f"🎰 Slots: **{row.slots_played}**\n"
        f"💰 Jackpots: **{row.jackpots}**\n"
        f"⚔️ Duels W/L: **{row.duels_won}/{row.duels_lost}**\n"
        f"🧠 Trivia W/L: **{row.trivia_won}/{row.trivia_lost}**"
    )


@command("greset", "Reset your game stats")
async def greset(e):
    me = await e.client.get_me()
    async with e.ctx.database.session() as s:
        r = await s.execute(select(GameStat).where(GameStat.user_id == me.id))
        row = r.scalar_one_or_none()
        if row:
            await s.delete(row)
    await e.edit(Messages.success("Game stats reset."))


@command("gameshelp", "Games help")
async def gameshelp(e):
    await e.edit(
        "🎮 `.dice .dart .bowl .basket .football .slot .8ball .coinflip "
        ".rps .duel .trivia .gstats .greset`"
    )
