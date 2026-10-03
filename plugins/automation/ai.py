"""AI — persistent chat memory with learned context, account-scoped.

Three tiers of memory per conversation:

  1. Raw turns      — last 500 messages (bounded)
  2. Summaries      — compressed batches of older turns (rolling)
  3. Profile        — "how this person talks" + recurring topics
                      (regenerated when enough new turns accumulate)

Every prompt sends: system + persona + profile + summaries + last 20 raw turns.
"""
import asyncio
import json
import random
import time
from pathlib import Path

from telethon import events

from Config.settings import Config
from core.decorators import command, listener
from core.module import ModuleMeta
from helpers.network.http import post_json
from utils import Messages, SEP_FANCY

META = ModuleMeta(
    name="ai", category="automation",
    description="Persistent context-aware chat memory (account-scoped).",
    permission="user",
)

MAX_HISTORY = 500          # raw turns kept per conversation
CONTEXT_WINDOW = 20        # raw turns sent per request
COOLDOWN = 3.0
PERSONA_CAP = 5000
PROFILE_CAP = 800          # learned profile is capped
PROFILE_MIN_TURNS = 12     # regenerate after this many new turns
PROFILE_REGEN_GAP = 6      # skip regen if < 6 new turns since last

SUMMARY_IDLE_SECONDS = 300     # summarize only after 5 min idle
SUMMARY_BATCH_MIN_TURNS = 6    # need this many new turns to summarize
SUMMARY_KEEP_TURNS = 30        # leave this many raw turns unsummarized

MOODS = {
    "friendly": "Warm, casual. Match the person's language mix.",
    "savage": "Witty, sarcastic, never cruel. Match their language.",
    "teacher": "Clear, patient, simple. Match their language.",
    "flirty": "Charming, playful, PG. Match their language.",
    "philosopher": "Reflective, short takes. Match their language.",
}

_STATE: dict = {}


# ═══════════════════════════════════════════════════════════════════
#  STATE MANAGEMENT (account-scoped, JSON on disk)
# ═══════════════════════════════════════════════════════════════════

def _state(ctx):
    st = _STATE.get(ctx.account_id)
    if st is None:
        st = {
            "dm_enabled": False,
            "context_mode": False,       # observe without replying
            "loaded": False,
            "histories": {},              # conv_key -> [ {role, content, ts} ]
            "summaries": {},              # conv_key -> [ {text, from_ts, to_ts, n} ]
            "profiles": {},               # chat_id  -> {text, updated_at, turns_seen}
            "personas": {},               # chat_id  -> user-set persona text
            "moods": {"global": "friendly"},
            "global_persona": "",
            "last_activity": {},          # conv_key -> ts
            "cool": {},                   # sender_id -> ts
        }
        _STATE[ctx.account_id] = st
    return st


def _store_path(ctx) -> Path:
    return ctx.paths.file("ai_state.json")


def _load(ctx):
    st = _state(ctx)
    if st["loaded"]:
        return
    p = _store_path(ctx)
    if not p.exists():
        st["loaded"] = True
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        st["loaded"] = True
        return

    st["dm_enabled"] = bool(data.get("dm_enabled", False))
    st["context_mode"] = bool(data.get("context_mode", False))
    st["histories"] = data.get("histories", {}) or {}
    st["summaries"] = data.get("summaries", {}) or {}
    st["profiles"] = data.get("profiles", {}) or {}
    st["personas"] = data.get("personas", {}) or {}
    st["moods"] = data.get("moods", {}) or {"global": "friendly"}
    st["global_persona"] = str(data.get("global_persona", ""))
    st["last_activity"] = {
        k: float(v) for k, v in (data.get("last_activity", {}) or {}).items()
    }
    st["loaded"] = True


def _save(ctx):
    st = _state(ctx)
    data = {
        "dm_enabled": st["dm_enabled"],
        "context_mode": st["context_mode"],
        "histories": st["histories"],
        "summaries": st["summaries"],
        "profiles": st["profiles"],
        "personas": st["personas"],
        "moods": st["moods"],
        "global_persona": st["global_persona"],
        "last_activity": st["last_activity"],
    }
    try:
        _store_path(ctx).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    except Exception:
        pass


def _conv_key(chat_id: int, sender_id: int) -> str:
    return f"{chat_id}:{sender_id}"


def _append_turn(ctx, key: str, role: str, content: str):
    st = _state(ctx)
    hist = st["histories"].setdefault(key, [])
    hist.append({"role": role, "content": content, "ts": time.time()})
    if len(hist) > MAX_HISTORY:
        del hist[:len(hist) - MAX_HISTORY]
    st["last_activity"][key] = time.time()


# ═══════════════════════════════════════════════════════════════════
#  GROQ ENDPOINT
# ═══════════════════════════════════════════════════════════════════

async def _ask(messages, max_tokens: int = 300) -> str | None:
    if not Config.GROQ_KEY:
        return None
    payload = {
        "model": Config.GROQ_MODELS[0],
        "messages": messages,
        "temperature": 0.9,
        "max_completion_tokens": max_tokens,
    }
    data = await post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {Config.GROQ_KEY}"},
    )
    if not data:
        return None
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _clean(text: str) -> str:
    return text.replace("**", "").replace("__", "").replace("`", "").strip()


def _humanize(text: str) -> str:
    text = " ".join((text or "").split())
    text = text.strip('"').strip("'")
    if len(text) > 400:
        text = text[:400].rstrip() + "…"
    return text


# ═══════════════════════════════════════════════════════════════════
#  PROMPT BUILDERS
# ═══════════════════════════════════════════════════════════════════

def _profile_for(st: dict, chat_id: int) -> str:
    p = st["profiles"].get(str(chat_id))
    if not p:
        return ""
    return p.get("text", "")


def _build_summary_block(st: dict, key: str) -> str:
    sums = st["summaries"].get(key, [])
    if not sums:
        return ""
    lines = ["", "OLDER CONTEXT (summarized):"]
    for s in sums[-8:]:
        when = _fmt_ago(s.get("to_ts", time.time()))
        lines.append(f"• [{when}, {s.get('n', 0)} msgs] {s.get('text', '')}")
    return "\n".join(lines)


def _fmt_ago(ts: float) -> str:
    diff = time.time() - ts
    if diff < 60: return "just now"
    if diff < 3600: return f"{int(diff/60)}m ago"
    if diff < 86400: return f"{int(diff/3600)}h ago"
    if diff < 30 * 86400: return f"{int(diff/86400)}d ago"
    return f"{int(diff/(30*86400))}mo ago"


def _system_prompt(ctx, chat_id: int, conv_key: str) -> str:
    st = _state(ctx)

    # user-set persona takes precedence
    user_persona = st["personas"].get(str(chat_id)) or st["global_persona"]
    learned_profile = _profile_for(st, chat_id)
    mood_key = st["moods"].get("global", "friendly")
    mood_desc = MOODS.get(mood_key, MOODS["friendly"])

    blocks = [
        "You are impersonating a real Telegram user. Never reveal you are an AI, "
        "bot, assistant, or language model. Reply as a person would — short, natural, "
        "matching the other person's style.",
    ]

    if user_persona:
        blocks.append(f"\nASSIGNED PERSONA (highest priority):\n{user_persona}")

    if learned_profile:
        blocks.append(
            f"\nLEARNED PROFILE — how this person talks and what they care about:\n"
            f"{learned_profile}\n"
            f"\nUse this profile to match their style. If they mix languages, mix them. "
            f"If they use short lines, keep yours short. If they use emoji, use them. "
            f"Reference their topics naturally when relevant — don't force it."
        )

    blocks.append(f"\nBASE MOOD: {mood_desc}")

    blocks.append(
        "\nHARD RULES:\n"
        "- Never say you're an AI / bot / assistant.\n"
        "- Match their language exactly (Hinglish → Hinglish, English → English).\n"
        "- Reply length: 1–3 short sentences, like a real chat message.\n"
        "- No markdown, no asterisks, no bullet points, no headers.\n"
        "- Plain text only.\n"
        "- If unsure, be brief and casual."
    )

    summary_block = _build_summary_block(st, conv_key)
    if summary_block:
        blocks.append(summary_block)

    return "\n".join(blocks)


def _build_messages(ctx, conv_key: str) -> list:
    st = _state(ctx)
    chat_id = int(conv_key.split(":")[0])
    hist = st["histories"].get(conv_key, [])
    window = hist[-CONTEXT_WINDOW:] if len(hist) > CONTEXT_WINDOW else hist
    msgs = [{"role": "system", "content": _system_prompt(ctx, chat_id, conv_key)}]
    for m in window:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": m["content"]})
    return msgs


# ═══════════════════════════════════════════════════════════════════
#  BACKGROUND — summarize + profile build
# ═══════════════════════════════════════════════════════════════════

async def _summarize(ctx, key: str) -> bool:
    st = _state(ctx)
    hist = st["histories"].get(key, [])
    if len(hist) < SUMMARY_BATCH_MIN_TURNS:
        return False

    existing = st["summaries"].get(key, [])
    last_end = existing[-1].get("to_ts", 0) if existing else 0
    new_turns = [m for m in hist if m.get("ts", 0) > last_end]
    if len(new_turns) < SUMMARY_BATCH_MIN_TURNS:
        return False

    # leave the most recent turns raw
    if len(new_turns) > SUMMARY_KEEP_TURNS:
        to_sum = new_turns[:-SUMMARY_KEEP_TURNS]
    else:
        to_sum = new_turns[:-3]

    if len(to_sum) < SUMMARY_BATCH_MIN_TURNS:
        return False

    lines = []
    for m in to_sum:
        who = "Them" if m["role"] == "user" else "Me"
        lines.append(f"{who}: {m['content']}")
    convo = "\n".join(lines)
    if len(convo) > 6000:
        convo = convo[-6000:]

    prompt = (
        "Summarize the following Telegram conversation between 'Me' (the account "
        "owner) and 'Them' (the other person). Focus on: who Them is, what they "
        "care about, recurring topics, current plans, emotional tone, and anything "
        "important to remember for future replies. Write from Me's perspective. "
        "1-3 sentences. Plain text. Under 60 words.\n\n" + convo
    )
    reply = await _ask(
        [{"role": "system", "content": "You summarize conversations."},
         {"role": "user", "content": prompt}],
        max_tokens=200,
    )
    if not reply:
        return False

    reply = _clean(reply)
    st["summaries"].setdefault(key, []).append({
        "text": reply,
        "from_ts": to_sum[0].get("ts", time.time()),
        "to_ts": to_sum[-1].get("ts", time.time()),
        "n": len(to_sum),
    })
    if len(st["summaries"][key]) > 40:
        st["summaries"][key] = st["summaries"][key][-40:]
    return True


async def _rebuild_profile(ctx, chat_id: int) -> bool:
    st = _state(ctx)
    key = f"{chat_id}:{chat_id}"  # DM conv key
    hist = st["histories"].get(key, [])
    if len(hist) < PROFILE_MIN_TURNS:
        return False

    # skip if we already have a fresh profile
    existing = st["profiles"].get(str(chat_id))
    if existing and len(hist) - existing.get("turns_seen", 0) < PROFILE_REGEN_GAP:
        return False

    # sample from the last 60 turns
    sample = hist[-60:]
    lines = []
    for m in sample:
        who = "Them" if m["role"] == "user" else "Me"
        lines.append(f"{who}: {m['content']}")
    convo = "\n".join(lines)
    if len(convo) > 5000:
        convo = convo[-5000:]

    prompt = (
        "Analyze the following Telegram conversation. Extract ONLY the following, "
        "as plain text, under 150 words total:\n"
        "1. How 'Them' writes: language mix, tone, formality, emoji use, typical "
        "message length, vocabulary quirks.\n"
        "2. Recurring topics or interests.\n"
        "3. Their name if it appears.\n"
        "4. Anything important to remember for future replies.\n\n"
        "Be concrete. No headers. Plain sentences.\n\n" + convo
    )
    reply = await _ask(
        [{"role": "system", "content": "You analyze chat style and extract profiles."},
         {"role": "user", "content": prompt}],
        max_tokens=300,
    )
    if not reply:
        return False

    reply = _clean(reply)[:PROFILE_CAP]
    st["profiles"][str(chat_id)] = {
        "text": reply,
        "updated_at": time.time(),
        "turns_seen": len(hist),
    }
    return True


async def _memory_worker(ctx):
    """Every 60s: summarize + rebuild profiles for idle conversations."""
    logger_tag = ctx.log_tag
    while True:
        try:
            await asyncio.sleep(60)
            st = _state(ctx)
            now = time.time()
            dirty = False

            # which conversations are idle?
            idle_keys = [
                k for k, ts in st["last_activity"].items()
                if now - ts >= SUMMARY_IDLE_SECONDS
            ]

            for key in idle_keys:
                if await _summarize(ctx, key):
                    dirty = True

                # profile rebuild is DM-only (chat_id == sender_id)
                try:
                    chat_id_str = key.split(":")[0]
                    if int(chat_id_str) == int(key.split(":")[1]):
                        if await _rebuild_profile(ctx, int(chat_id_str)):
                            dirty = True
                except Exception:
                    pass

            if dirty:
                _save(ctx)
        except asyncio.CancelledError:
            return
        except Exception as e:
            # never let the worker die
            try:
                from core.logger import setup_logger
                setup_logger("VECTOR.ai").error(
                    f"{logger_tag} memory worker: {e}", exc_info=True
                )
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════════

@command(r"ai (.+)", "Ask the AI (with learned context)")
async def ai_handler(event):
    ctx = event.ctx
    _load(ctx)
    text = event.pattern_match.group(1).strip()
    key = _conv_key(event.chat_id, event.sender_id)

    _append_turn(ctx, key, "user", text)
    msgs = _build_messages(ctx, key)

    reply = await _ask(msgs)
    if not reply:
        # roll back the failed turn
        st = _state(ctx)
        if st["histories"].get(key):
            st["histories"][key].pop()
        await event.edit(Messages.error("AI unavailable."))
        return

    _append_turn(ctx, key, "assistant", reply)
    _save(ctx)

    st = _state(ctx)
    profile_mark = "📖" if st["profiles"].get(str(event.chat_id)) else "·"
    summary_count = len(st["summaries"].get(key, []))
    await event.edit(
        f"🤖 **VECTOR** {profile_mark}\n{SEP_FANCY}\n{reply}\n{SEP_FANCY}\n"
        f"_profile · {summary_count} summaries · "
        f"{len(st['histories'].get(key, []))} turns_"
    )


@command(r"aion(?:\s+(on|off))?", "Toggle DM auto-reply")
async def aion(event):
    ctx = event.ctx
    _load(ctx)
    st = _state(ctx)
    arg = (event.pattern_match.group(1) or "").lower()
    if arg:
        st["dm_enabled"] = arg == "on"
        _save(ctx)
    state = "🟢 ON" if st["dm_enabled"] else "🔴 OFF"
    await event.edit(Messages.info(f"DM auto-reply: **{state}**"))


@command(r"aicontext(?:\s+(on|off))?", "Observe + learn without replying")
async def aicontext(event):
    ctx = event.ctx
    _load(ctx)
    st = _state(ctx)
    arg = (event.pattern_match.group(1) or "").lower()
    if arg:
        st["context_mode"] = arg == "on"
        _save(ctx)
    state = "🟢 ON" if st["context_mode"] else "🔴 OFF"
    await event.edit(Messages.info(
        f"Context learning: **{state}**\n"
        f"_When on, incoming DMs are stored and profiled but NOT auto-replied._"
    ))


@command(r"aimood(?:\s+(\w+))?", "Set base mood")
async def aimood(event):
    ctx = event.ctx
    _load(ctx)
    st = _state(ctx)
    arg = (event.pattern_match.group(1) or "").strip().lower()
    if not arg:
        cur = st["moods"].get("global", "friendly")
        await event.edit(Messages.info(
            f"Mood: **{cur}**\nOptions: {', '.join(MOODS.keys())}"
        ))
        return
    if arg not in MOODS:
        await event.edit(Messages.error(f"Unknown `{arg}`."))
        return
    st["moods"]["global"] = arg
    _save(ctx)
    await event.edit(Messages.success(f"Mood: **{arg}**."))


@command(r"aihuman(?:\s+([\s\S]+))?", "Set assigned persona for this chat")
async def aihuman(event):
    ctx = event.ctx
    _load(ctx)
    st = _state(ctx)
    key = str(event.chat_id)
    arg = (event.pattern_match.group(1) or "").strip()
    if not arg:
        persona = st["personas"].get(key) or st["global_persona"]
        preview = persona[:1000] if persona else "—"
        await event.edit(Messages.info(
            f"Assigned persona:\n\n{preview}\n\n"
            f"_This overrides the learned profile._"
        ))
        return
    if arg.lower() == "clear":
        st["personas"].pop(key, None)
        _save(ctx)
        await event.edit(Messages.success("Assigned persona cleared."))
        return
    st["personas"][key] = arg[:PERSONA_CAP]
    _save(ctx)
    await event.edit(Messages.success(f"Assigned persona set ({len(arg)} chars)."))


@command(r"aiclear(?:\s+(\w+))?", "Clear memory for this conversation")
async def aiclear(event):
    ctx = event.ctx
    _load(ctx)
    st = _state(ctx)
    key = _conv_key(event.chat_id, event.sender_id)
    arg = (event.pattern_match.group(1) or "").strip().lower()

    if arg == "all":
        n = len(st["histories"]) + len(st["summaries"]) + len(st["profiles"])
        st["histories"].clear()
        st["summaries"].clear()
        st["profiles"].clear()
        st["last_activity"].clear()
        _save(ctx)
        await event.edit(Messages.success(f"Cleared {n} record(s)."))
        return

    if arg == "profile":
        st["profiles"].pop(str(event.chat_id), None)
        _save(ctx)
        await event.edit(Messages.success("Learned profile cleared."))
        return

    st["histories"].pop(key, None)
    st["summaries"].pop(key, None)
    st["last_activity"].pop(key, None)
    _save(ctx)
    await event.edit(Messages.success("Conversation memory cleared."))


@command(r"airecall(?: (.+))?", "Search this conversation's history")
async def airecall(event):
    ctx = event.ctx
    _load(ctx)
    st = _state(ctx)
    key = _conv_key(event.chat_id, event.sender_id)
    hist = st["histories"].get(key, [])
    if not hist:
        await event.edit(Messages.info("No memory for this chat."))
        return
    q = (event.pattern_match.group(1) or "").strip().lower()
    if q:
        matches = [m for m in hist if q in (m.get("content") or "").lower()]
        if not matches:
            await event.edit(Messages.info(f"No matches for `{q}`."))
            return
        lines = [f"🔎 **{len(matches)} match(es)**", SEP_FANCY]
        for m in matches[-10:]:
            who = "👤" if m["role"] == "user" else "🤖"
            when = _fmt_ago(m.get("ts", time.time()))
            lines.append(f"{who} _{m['content'][:80]}_ ({when})")
        await event.edit("\n".join(lines))
        return
    recent = hist[-15:]
    lines = [f"📜 **Last {len(recent)} turns**", SEP_FANCY]
    for m in recent:
        who = "👤" if m["role"] == "user" else "🤖"
        lines.append(f"{who} _{m['content'][:80]}_")
    await event.edit("\n".join(lines))


@command("aisummary", "Force-summarize this conversation")
async def aisummary(event):
    ctx = event.ctx
    _load(ctx)
    key = _conv_key(event.chat_id, event.sender_id)
    await event.edit(Messages.loading("Summarizing…"))
    if await _summarize(ctx, key):
        _save(ctx)
        s = _state(ctx)["summaries"][key][-1]
        await event.edit(
            f"📝 **Summary added**\n{SEP_FANCY}\n{s['text']}\n{SEP_FANCY}\n"
            f"_covered {s['n']} turns_"
        )
    else:
        await event.edit(Messages.info(
            f"Not enough new content.\n"
            f"_Need {SUMMARY_BATCH_MIN_TURNS}+ new turns._"
        ))


@command("aisummaries", "List summaries for this conversation")
async def aisummaries(event):
    ctx = event.ctx
    _load(ctx)
    key = _conv_key(event.chat_id, event.sender_id)
    sums = _state(ctx)["summaries"].get(key, [])
    if not sums:
        await event.edit(Messages.info("No summaries yet."))
        return
    lines = [f"📝 **{len(sums)} summary(ies)**", SEP_FANCY]
    for s in sums[-10:]:
        when = _fmt_ago(s.get("to_ts", time.time()))
        lines.append(f"\n**{when}** ({s.get('n', 0)} msgs)\n_{s.get('text', '')}_")
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[-3900:]
    await event.edit(text)


@command("aiprofile", "Show or rebuild the learned profile for this chat")
async def aiprofile(event):
    ctx = event.ctx
    _load(ctx)
    st = _state(ctx)
    p = st["profiles"].get(str(event.chat_id))
    if p is None:
        await event.edit(Messages.info(
            "No profile yet.\n"
            "_Send more messages or use `.aicontext on`._"
        ))
        return
    when = _fmt_ago(p.get("updated_at", time.time()))
    await event.edit(
        f"📖 **LEARNED PROFILE**\n{SEP_FANCY}\n"
        f"{p.get('text', '—')}\n{SEP_FANCY}\n"
        f"_updated {when} · {p.get('turns_seen', 0)} turns seen_"
    )


@command("aiprofilerebuild", "Rebuild the learned profile now")
async def aiprofilerebuild(event):
    ctx = event.ctx
    _load(ctx)
    await event.edit(Messages.loading("Analyzing conversation…"))
    ok = await _rebuild_profile(ctx, event.chat_id)
    if ok:
        _save(ctx)
        await event.edit(Messages.success(
            "Profile rebuilt. Use `.aiprofile` to see it."
        ))
    else:
        await event.edit(Messages.info(
            f"Not enough data. Need {PROFILE_MIN_TURNS}+ turns."
        ))


@command("aistatus", "AI status")
async def aistatus(event):
    ctx = event.ctx
    _load(ctx)
    st = _state(ctx)
    total_turns = sum(len(h) for h in st["histories"].values())
    total_sums = sum(len(s) for s in st["summaries"].values())
    await event.edit(
        f"🤖 **AI STATUS**\n{SEP_FANCY}\n"
        f"**DM auto-reply**   {'🟢' if st['dm_enabled'] else '🔴'}\n"
        f"**Context learn**   {'🟢' if st['context_mode'] else '🔴'}\n"
        f"**Conversations**   {len(st['histories'])}\n"
        f"**Total turns**     {total_turns}\n"
        f"**Summaries**       {total_sums}\n"
        f"**Learned profiles** {len(st['profiles'])}\n"
        f"**Assigned personas** {len(st['personas'])}\n"
        f"**Mood**            {st['moods'].get('global', 'friendly')}\n"
        f"{SEP_FANCY}\n"
        f"_Context window: {CONTEXT_WINDOW} · Raw cap: {MAX_HISTORY}_"
    )


@command("aihelp", "AI help")
async def aihelp(event):
    await event.edit(
        "🤖 **AI — CONTEXT-AWARE**\n"
        f"{SEP_FANCY}\n\n"
        "**Chat:**\n"
        "▸ `.ai <message>` — ask / chat\n\n"
        "**Auto behaviors:**\n"
        "▸ `.aion on|off` — auto-reply to incoming DMs\n"
        "▸ `.aicontext on|off` — observe + learn, don't reply\n\n"
        "**Style control:**\n"
        "▸ `.aimood <mood>` — base tone\n"
        "▸ `.aihuman <text>` — assigned persona (overrides learned)\n"
        "▸ `.aihuman clear` — remove assigned persona\n\n"
        "**Inspect memory:**\n"
        "▸ `.aiprofile` — learned 'how they talk' profile\n"
        "▸ `.aiprofile rebuild` — regenerate now\n"
        "▸ `.aisummary` — force-summarize this chat\n"
        "▸ `.aisummaries` — list summaries\n"
        "▸ `.airecall [query]` — search history\n"
        "▸ `.aistatus` — memory stats\n\n"
        "**Clear:**\n"
        "▸ `.aiclear` — this conversation\n"
        "▸ `.aiclear profile` — learned profile only\n"
        "▸ `.aiclear all` — everything\n\n"
        f"{SEP_FANCY}\n"
        "**How it learns:**\n"
        "• Stores last 500 turns per chat\n"
        "• Every 5 min idle → summarizes older turns\n"
        "• After 12+ turns → builds a 'how they talk' profile\n"
        "• Every reply sends: system + persona + profile + summaries + last 20 turns"
    )


# ═══════════════════════════════════════════════════════════════════
#  LISTENERS
# ═══════════════════════════════════════════════════════════════════

@listener(events.NewMessage(incoming=True))
async def ai_watcher(event):
    ctx = getattr(event.client, "ctx", None)
    if ctx is None or not event.raw_text:
        return
    _load(ctx)
    st = _state(ctx)

    if not event.is_private:
        return
    if event.raw_text.startswith(Config.CMD_PREFIX):
        return

    me = await event.client.get_me()
    if event.sender_id == me.id:
        return

    try:
        sender = await event.get_sender()
        if sender is None or getattr(sender, "bot", False):
            return
    except Exception:
        return

    key = _conv_key(event.chat_id, event.sender_id)

    # Always store if either mode is on
    if not (st["dm_enabled"] or st["context_mode"]):
        return

    _append_turn(ctx, key, "user", event.raw_text)

    # Only reply if auto-reply mode is on
    if not st["dm_enabled"]:
        _save(ctx)
        return

    # Cooldown
    now = time.time()
    if now - st["cool"].get(event.sender_id, 0) < COOLDOWN:
        _save(ctx)
        return
    st["cool"][event.sender_id] = now

    msgs = _build_messages(ctx, key)
    reply = await _ask(msgs)
    if not reply:
        return

    _append_turn(ctx, key, "assistant", reply)
    _save(ctx)

    reply = _humanize(reply)
    delay = random.uniform(0.8, 2.2)
    try:
        async with event.client.action(event.chat_id, "typing"):
            await asyncio.sleep(delay)
    except Exception:
        await asyncio.sleep(delay)
    try:
        await event.reply(reply)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════════════

async def on_startup(ctx):
    _load(ctx)
    return asyncio.create_task(_memory_worker(ctx))