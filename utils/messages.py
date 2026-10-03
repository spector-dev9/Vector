"""Consistent message formatting."""

# separators
SEP_SHORT = "─" * 20
SEP_LONG = "─" * 30
SEP_FANCY = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


class Messages:
    # ═══════════════════════════════════════════════════════
    #  one-liners — compact, single line
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def success(t):
        """✅ Saved DP #1"""
        return f"✅ {t}"

    @staticmethod
    def error(t):
        """❌ Usage: .save dp <n> (reply)."""
        return f"❌ {t}"

    @staticmethod
    def warning(t):
        """⚠️ Cooldown 15s"""
        return f"⚠️ {t}"

    @staticmethod
    def info(t):
        """ℹ️ No presets saved."""
        return f"ℹ️ {t}"

    @staticmethod
    def loading(t="Processing…"):
        """⏳ Building zip…"""
        return f"⏳ {t}"

    @staticmethod
    def ok(t):
        return f"✅ {t}"

    @staticmethod
    def err(t):
        return f"❌ {t}"

    @staticmethod
    def warn(t):
        return f"⚠️ {t}"

    @staticmethod
    def note(t):
        return f"ℹ️ {t}"

    # ═══════════════════════════════════════════════════════
    #  card — structured dashboard for multi-line output
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def card(emoji, title, rows=None, subtitle="", footer="", sep=SEP_FANCY):
        """
        Structured card.

            ⚡ **VECTOR STATUS**
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            **account**    main
            **uptime**     2h 15m
            **commands**   43
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            _v2.1.0 · prefix `.`_

        rows: list of ("key", "value") tuples, or plain strings
        """
        lines = [f"{emoji} **{title.upper()}**"]
        if subtitle:
            lines.append(f"_{subtitle}_")
        lines.append(sep)
        if rows:
            for r in rows:
                if isinstance(r, tuple):
                    k, v = r
                    lines.append(f"**{k}**   {v}")
                else:
                    lines.append(str(r))
            lines.append(sep)
        if footer:
            lines.append(f"_{footer}_")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════
    #  section — sub-header inside a card / longer message
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def section(title, items=None, bullet="▸"):
        """
        **Tools** · 12
        ▸ ping
        ▸ alive
        ...
        """
        lines = [f"**{title}**"]
        for item in (items or []):
            lines.append(f"{bullet} {item}")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════
    #  helpers
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def header(emoji, title, subtitle=""):
        out = f"{emoji} **{title.upper()}**"
        if subtitle:
            out += f"\n_{subtitle}_"
        return out + f"\n{SEP_FANCY}"

    @staticmethod
    def key_value(k, v):
        return f"**{k}:** {v}"

    @staticmethod
    def format_key_value(k, v):
        return f"**{k}:** {v}"

    @staticmethod
    def bullets(items, bullet="•"):
        return "\n".join(f"{bullet} {x}" for x in items)

    @staticmethod
    def code(text, lang=""):
        return f"```{lang}\n{text}\n```"

    @staticmethod
    def inline_code(text):
        return f"`{text}`"

    @staticmethod
    def bold(text):
        return f"**{text}**"

    @staticmethod
    def dim(text):
        return f"_{text}_"

    @staticmethod
    def sep(kind="fancy"):
        return {"short": SEP_SHORT, "long": SEP_LONG, "fancy": SEP_FANCY}.get(
            kind, SEP_FANCY
        )