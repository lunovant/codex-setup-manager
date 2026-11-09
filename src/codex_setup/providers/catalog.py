"""Provider presets and input validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from codex_setup.core.errors import ReservedProviderError, ValidationError

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

# Mirrors codex_config.RESERVED_PROVIDER_IDS (kept here to avoid a circular import).
_RESERVED = frozenset({"openai", "ollama", "lmstudio", "amazon-bedrock", "gcp"})


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    base_url: str
    env_key: str | None
    wire_api: str = "responses"
    builtin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "env_key": self.env_key,
            "wire_api": self.wire_api,
            "builtin": self.builtin,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProviderSpec:
        return cls(
            id=str(d["id"]),
            name=str(d.get("name", d["id"])),
            base_url=str(d["base_url"]),
            env_key=d.get("env_key"),
            wire_api=str(d.get("wire_api", "responses")),
            builtin=bool(d.get("builtin", False)),
        )


LUNOVANT_ROOT_URL = "https://api.lunovant.tech"
LUNOVANT = ProviderSpec("lunovant", "Lunovant", "https://api.lunovant.tech/v1", "LUNOVANT_API_KEY")
LUNOVANT_MODELS = ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-sol", "gpt-6-luna", "gpt-6-astra")
DEFAULT_MODEL = "gpt-6.1-sol"
OPENAI = ProviderSpec(
    "openai", "OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY", builtin=True
)


def normalize_base_url(url: str) -> str:
    raw = (url or "").strip()
    try:
        parts = urlsplit(raw)
        host = parts.hostname
    except ValueError as exc:
        raise ValidationError(f"Invalid URL: {raw!r}") from exc
    if parts.scheme not in ("http", "https") or not host:
        raise ValidationError(f"URL must start with http:// or https:// and include a host: {raw!r}")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise ValidationError(
            "URL must not contain credentials (user:pass@host); store the key with --key-stdin"
        )
    if "?" in raw:
        raise ValidationError(
            "URL must not contain a query string; Codex base_url needs none "
            "(extra parameters belong in query_params)"
        )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")


def suggest_v1(url: str) -> str:
    normalized = normalize_base_url(url)
    parts = urlsplit(normalized)
    if parts.path.endswith("/v1"):
        return normalized
    return urlunsplit((parts.scheme, parts.netloc, parts.path + "/v1", parts.query, ""))


def validate_model_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ValidationError("Model name must not be empty")
    if len(value) > 128:
        raise ValidationError("Model name is too long (max 128 characters)")
    if re.search(r"\s", value) or '"' in value or "'" in value:
        raise ValidationError("Model name must not contain whitespace or quotes")
    return value


def validate_provider_id(provider_id: str) -> str:
    if not _ID_RE.match(provider_id or ""):
        raise ValidationError(
            f"Invalid provider id {provider_id!r}: use lowercase letters, digits, '-' or '_'"
        )
    return provider_id


def validate_env_key(env_key: str) -> str:
    if not _ENV_RE.match(env_key or ""):
        raise ValidationError(
            f"Invalid environment variable name {env_key!r}: use A-Z, 0-9 and '_'"
        )
    return env_key


def custom_provider(id: str, name: str, base_url: str, env_key: str) -> ProviderSpec:
    validate_provider_id(id)
    if id in _RESERVED:
        raise ReservedProviderError(f"Provider id {id!r} is reserved by Codex")
    validate_env_key(env_key)
    display = (name or "").strip() or id
    return ProviderSpec(id, display, normalize_base_url(base_url), env_key)
