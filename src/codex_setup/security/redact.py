"""Mask secrets before they reach logs, reports or the screen."""

from __future__ import annotations

import re
from collections.abc import Iterable

_BEARER = re.compile(r"(?i)\b(Bearer)(\s+)([A-Za-z0-9._~+/=\-]+)")


def mask_key(key: str | None) -> str:
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}…{key[-4:]}"


def redact(text: str, secrets: Iterable[str]) -> str:
    """Mask every secret (len >= 4) and any ``Bearer <token>`` pattern."""
    if not text:
        return text
    text = _BEARER.sub(lambda m: f"{m.group(1)}{m.group(2)}{mask_key(m.group(3))}", text)
    unique = sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True)
    for secret in unique:
        text = text.replace(secret, mask_key(secret))
    return text
