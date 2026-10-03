"""Validation utilities."""
from __future__ import annotations
import re
from typing import Optional, Union

_USERNAME_RX = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_URL_RX = re.compile(r"^https?://[^\s]+$")
_TG_LINK_RX = re.compile(r"tg://user\?id=(\d+)")


class Validators:
    @staticmethod
    def is_valid_username(username: str) -> bool:
        return bool(username and _USERNAME_RX.match(username))

    @staticmethod
    def is_valid_user_id(user_id: Union[str, int]) -> bool:
        s = str(user_id)
        return s.lstrip("-").isdigit() and len(s) <= 20

    @staticmethod
    def is_valid_url(url: str) -> bool:
        return bool(url and _URL_RX.match(url))

    @staticmethod
    def extract_user_id(text: str) -> Optional[int]:
        if not text:
            return None
        m = _TG_LINK_RX.search(text)
        if m:
            return int(m.group(1))
        if text.lstrip("-").isdigit():
            return int(text)
        return None

    @staticmethod
    def parse_user_or_id(arg: str) -> Optional[Union[int, str]]:
        """int for numeric ids, str (with @) for usernames, None otherwise."""
        arg = (arg or "").strip()
        if not arg:
            return None
        if arg.startswith("@") and len(arg) > 1:
            return arg
        if arg.lstrip("-").isdigit():
            try:
                return int(arg)
            except ValueError:
                return None
        return None
