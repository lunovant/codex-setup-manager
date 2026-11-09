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


_SENSITIVE_KV = re.compile(
    r"""(?P<key>"?[A-Za-z0-9_.\-]*(?:authorization|api[_-]?key|token|secret|password|bearer)[A-Za-z0-9_.\-]*"?)"""
    r"""(?P<eq>\s*=\s*)(?P<val>"(?:[^"\\\n]|\\.)*"|'[^'\n]*')""",
    re.IGNORECASE,
)


def redact_config_text(text: str, secrets: Iterable[str]) -> str:
    """Mask known secrets and string values of sensitive TOML keys (also in inline tables).

    For DISPLAY only (diffs); never use the result as file content.
    """
    if not text:
        return text
    text = redact(text, secrets)
    return _SENSITIVE_KV.sub(lambda m: f'{m.group("key")}{m.group("eq")}"****"', text)
