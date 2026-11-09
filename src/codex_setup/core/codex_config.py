"""Pure tomlkit edits for Codex config.toml (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import tomlkit
from tomlkit.items import Comment, Table
from tomlkit.toml_document import TOMLDocument

from codex_setup.core.errors import ReservedProviderError, ValidationError
from codex_setup.providers.catalog import (
    ProviderSpec,
    validate_model_name,
    validate_provider_id,
)

RESERVED_PROVIDER_IDS = frozenset({"openai", "ollama", "lmstudio", "amazon-bedrock", "gcp"})


@dataclass
class ConfigStatus:
    model: str | None
    model_provider: str | None
    provider_ids: list[str]
    windows_sandbox: str | None
    active_provider: dict[str, Any] | None


def _plain(value: Any) -> Any:
    return value.unwrap() if hasattr(value, "unwrap") else value


def _providers(doc: TOMLDocument) -> Any | None:
    value = doc.get("model_providers")
    return value if isinstance(value, dict) else None


def get_status(doc: TOMLDocument) -> ConfigStatus:
    model = doc.get("model")
    provider = doc.get("model_provider")
    providers = _providers(doc)
    ids = [str(k) for k in providers.keys()] if providers is not None else []
    windows = doc.get("windows")
    sandbox = windows.get("sandbox") if isinstance(windows, dict) else None
    active: dict[str, Any] | None = None
    if providers is not None and provider is not None and str(provider) in providers:
        active = _plain(providers[str(provider)])
    return ConfigStatus(
        model=str(model) if model is not None else None,
        model_provider=str(provider) if provider is not None else None,
        provider_ids=ids,
        windows_sandbox=str(sandbox) if sandbox is not None else None,
        active_provider=active,
    )


def _check_id(provider_id: str) -> None:
    validate_provider_id(provider_id)
    if provider_id in RESERVED_PROVIDER_IDS:
        raise ReservedProviderError(f"Provider id {provider_id!r} is reserved by Codex")


def _detach_trailing_comments(providers: Any) -> list[Any]:
    """Pull comments that trail the last child table (they belong to what follows).

    tomlkit attaches a comment sitting between two tables to the preceding table.
    Appending a new table after it would put that comment above our table, so the
    comment (and anything after it) is moved to the end of the new table instead.
    """
    body = getattr(getattr(providers, "value", None), "body", None)
    if not body or not isinstance(body[-1][1], Table):
        return []
    return _detach_comments(body[-1][1])


def _detach_comments(table: Table) -> list[Any]:
    child_body = table.value.body
    start = len(child_body)
    while start > 0 and child_body[start - 1][0] is None:
        start -= 1
    first_comment = next(
        (i for i in range(start, len(child_body)) if isinstance(child_body[i][1], Comment)),
        None,
    )
    if first_comment is None:
        return []
    moved = [item for _, item in child_body[first_comment:]]
    del child_body[first_comment:]
    return moved


def upsert_provider(doc: TOMLDocument, spec: ProviderSpec) -> None:
    _check_id(spec.id)
    if spec.env_key is None:
        raise ValidationError("A custom provider needs env_key")
    values = {
        "name": spec.name,
        "base_url": spec.base_url,
        "env_key": spec.env_key,
        "wire_api": spec.wire_api,
    }
    providers = doc.get("model_providers")
    if providers is None:
        container = tomlkit.table(is_super_table=True)
        doc.add("model_providers", container)
        providers = doc["model_providers"]
    existing = providers.get(spec.id)
    if existing is None:
        table = tomlkit.table()
        for k, v in values.items():
            table.add(k, v)
        moved = _detach_trailing_comments(providers)
        for item in moved:
            table.append(None, item)
        if not moved:
            table.add(tomlkit.nl())
        providers.add(spec.id, table)
        return
    for k, v in values.items():
        if k in existing and existing[k] == v:
            continue  # leave untouched to keep formatting
        existing[k] = v


def _hand_comments_to_previous(providers: Any, provider_id: str) -> None:
    """Keep comments that trail the removed table (they belong to what follows it)."""
    body = getattr(getattr(providers, "value", None), "body", None)
    if not body:
        return
    for idx, (key, item) in enumerate(body):
        if key is not None and key.key == provider_id and isinstance(item, Table) and idx > 0:
            previous = body[idx - 1][1]
            if isinstance(previous, Table):
                for moved in _detach_comments(item):
                    previous.append(None, moved)
            return


def remove_provider(doc: TOMLDocument, provider_id: str) -> bool:
    providers = _providers(doc)
    if providers is None or provider_id not in providers:
        return False
    _hand_comments_to_previous(providers, provider_id)
    del providers[provider_id]
    if len(providers) == 0:
        del doc["model_providers"]
    return True


def _set_top_level(doc: TOMLDocument, key: str, value: str) -> None:
    if key in doc:
        if doc[key] != value:
            doc[key] = value
        return
    doc.add(key, value)  # tomlkit places scalars before the first table


def _remove_top_level(doc: TOMLDocument, key: str) -> None:
    if key in doc:
        del doc[key]


def set_active(doc: TOMLDocument, provider_id: str, model: str) -> None:
    validate_provider_id(provider_id)
    model = validate_model_name(model)
    _set_top_level(doc, "model_provider", provider_id)
    _set_top_level(doc, "model", model)


def set_model(doc: TOMLDocument, model: str) -> None:
    _set_top_level(doc, "model", validate_model_name(model))


def restore_top_level(doc: TOMLDocument, model: str | None, model_provider: str | None) -> None:
    for key, value in (("model", model), ("model_provider", model_provider)):
        if value is None:
            _remove_top_level(doc, key)
        else:
            _set_top_level(doc, key, value)


def set_windows_sandbox(
    doc: TOMLDocument, mode: Literal["elevated", "unelevated"] | None
) -> None:
    if mode is None:
        windows = doc.get("windows")
        if not isinstance(windows, dict):
            return
        windows.pop("sandbox", None)
        if len(windows) == 0:
            del doc["windows"]
        return
    if mode not in ("elevated", "unelevated"):
        raise ValidationError(f"Unsupported sandbox mode: {mode!r}")
    windows = doc.get("windows")
    if windows is None:
        table = tomlkit.table()
        table.add("sandbox", mode)
        doc.add("windows", table)
        return
    if windows.get("sandbox") != mode:
        windows["sandbox"] = mode


__all__ = [
    "RESERVED_PROVIDER_IDS",
    "ConfigStatus",
    "get_status",
    "remove_provider",
    "restore_top_level",
    "set_active",
    "set_model",
    "set_windows_sandbox",
    "upsert_provider",
]
