"""HTTP helpers with SSRF guard."""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from core.logger import setup_logger

logger = setup_logger("VECTOR.http")

TIMEOUT = 15


def _is_private_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        )
    except ValueError:
        pass
    try:
        resolved = socket.gethostbyname(host)
        ip = ipaddress.ip_address(resolved)
        return (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        )
    except Exception:
        return True


def is_safe_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        if not p.hostname:
            return False
        return not _is_private_host(p.hostname)
    except Exception:
        return False


async def get_json(url: str, **params):
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, params=params or None)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.debug(f"get_json {url}: {e}")
        return None


async def post_json(url: str, payload: dict, headers: dict | None = None):
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(url, json=payload, headers=headers or {})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.debug(f"post_json {url}: {e}")
        return None


async def fetch_text(url: str, **params) -> str | None:
    if not is_safe_url(url):
        logger.warning(f"fetch_text refused (unsafe): {url}")
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, params=params or None)
            r.raise_for_status()
            return r.text
    except Exception as e:
        logger.debug(f"fetch_text {url}: {e}")
        return None
