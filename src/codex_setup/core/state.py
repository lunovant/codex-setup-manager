"""App-owned state (profiles, managed providers). Never stores secrets."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from codex_setup.core import paths
from codex_setup.core.config_store import atomic_write_text
from codex_setup.providers.catalog import ProviderSpec


@dataclass
class Profile:
    name: str
    provider: ProviderSpec
    model: str
    models: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider.to_dict(),
            "model": self.model,
            "models": list(self.models),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Profile:
        return cls(
            name=str(d["name"]),
            provider=ProviderSpec.from_dict(d["provider"]),
            model=str(d["model"]),
            models=[str(m) for m in d.get("models", [])],
        )


@dataclass
class AppState:
    version: int = 1
    profiles: dict[str, Profile] = field(default_factory=dict)
    active_profile: str | None = None
    managed_provider_ids: list[str] = field(default_factory=list)
    original_top_level: dict[str, Any] | None = None
    original_snapshot: str | None = None
    secret_backend: str | None = None
    last_test: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profiles": {k: p.to_dict() for k, p in self.profiles.items()},
            "active_profile": self.active_profile,
            "managed_provider_ids": list(self.managed_provider_ids),
            "original_top_level": self.original_top_level,
            "original_snapshot": self.original_snapshot,
            "secret_backend": self.secret_backend,
            "last_test": self.last_test,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AppState:
        return cls(
            version=int(d.get("version", 1)),
            profiles={k: Profile.from_dict(v) for k, v in d.get("profiles", {}).items()},
            active_profile=d.get("active_profile"),
            managed_provider_ids=[str(i) for i in d.get("managed_provider_ids", [])],
            original_top_level=d.get("original_top_level"),
            original_snapshot=d.get("original_snapshot"),
            secret_backend=d.get("secret_backend"),
            last_test=d.get("last_test"),
        )


def state_path(env: Mapping[str, str] | None = None):
    return paths.app_state_dir(env) / "state.json"


def load_state(env: Mapping[str, str] | None = None) -> AppState:
    path = state_path(env)
    if not path.exists():
        return AppState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state root must be an object")
        return AppState.from_dict(data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        bad = path.with_name("state.json.bad")
        try:
            path.replace(bad)
        except OSError:
            pass
        return AppState()


def save_state(state: AppState, env: Mapping[str, str] | None = None) -> None:
    text = json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(state_path(env), text)
