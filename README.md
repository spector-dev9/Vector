# V E C T O R

Multi-account Telegram userbot.

## Setup
1. `cp .env.example .env`, fill API_ID, API_HASH, ACCOUNTS, PHONE_MAIN
2. `pip install -r requirements.txt`
3. `python verify.py` — structural check
4. `python audit.py`  — interface check
5. `python main.py`   — boots all accounts

Requires **ffmpeg** on PATH for `.yta` / `.ytv`.

Each account gets its own `data/accounts/<id>/` (DB, session, cache, files).

## Optional controller
Set `CONTROL_BOT_TOKEN` and `CONTROL_BOT_ADMIN_ID`, then `python controller.py`.
Provides `/start /stop /restart /status /logs`.

## Adding an account
Add its id to `ACCOUNTS`, set `PHONE_<ID>` or `SESSION_STRING_<ID>`.

## Adding a plugin
Create `plugins/<category>/<name>.py`, declare `META`, decorate with
`@command(...)` or `@listener(...)`. Restart, or `.modreload <name>`.
