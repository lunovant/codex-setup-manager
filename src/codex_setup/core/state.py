"""App-owned state (profiles, managed providers). Never stores secrets."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
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


_PROVIDER_FIELDS = ("name", "base_url", "env_key", "wire_api")


@dataclass
class ConfigOwnership:
    """What this tool changed in ONE config.toml (keyed by resolved path in AppState.configs)."""

    managed_provider_ids: list[str] = field(default_factory=list)
    original_top_level: dict[str, Any] | None = None
    original_snapshot: str | None = None
    # provider id -> previous value of name/base_url/env_key/wire_api (None = key was absent)
    overwritten: dict[str, dict[str, str | None]] = field(default_factory=dict)
    # provider id -> values this tool wrote into a pre-existing (non-managed) table
    written: dict[str, dict[str, str]] = field(default_factory=dict)
    # secret backend name -> env_keys this tool stored a secret for
    credentials: dict[str, list[str]] = field(default_factory=dict)
    # env_key -> persistent env install record (never holds the installed secret)
    env_installs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (
            self.managed_provider_ids
            or self.original_top_level is not None
            or self.original_snapshot is not None
            or self.overwritten
            or self.written
            or self.credentials
            or self.env_installs
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "managed_provider_ids": list(self.managed_provider_ids),
            "original_top_level": self.original_top_level,
            "original_snapshot": self.original_snapshot,
            "overwritten": self.overwritten,
            "written": self.written,
            "credentials": {k: list(v) for k, v in self.credentials.items()},
            "env_installs": self.env_installs,
        }

    @classmethod
    def from_dict(cls, d: Any) -> ConfigOwnership:
        _expect(d, dict, "config entry")
        ids = _str_list(d.get("managed_provider_ids", []), "managed_provider_ids")
        top = d.get("original_top_level")
        if top is not None:
            _expect(top, dict, "original_top_level")
        snap = d.get("original_snapshot")
        if snap is not None:
            _expect(snap, str, "original_snapshot")
        overwritten = _expect(d.get("overwritten", {}), dict, "overwritten")
        for pid, fields_ in overwritten.items():
            _expect(fields_, dict, "overwritten entry")
            for k, v in fields_.items():
                if k not in _PROVIDER_FIELDS or not (v is None or isinstance(v, str)):
                    raise ValueError("malformed overwritten entry")
        written = _expect(d.get("written", {}), dict, "written")
        for pid, fields_ in written.items():
            _expect(fields_, dict, "written entry")
            for k, v in fields_.items():
                if k not in _PROVIDER_FIELDS or not isinstance(v, str):
                    raise ValueError("malformed written entry")
        creds = _expect(d.get("credentials", {}), dict, "credentials")
        credentials = {str(k): _str_list(v, "credentials") for k, v in creds.items()}
        installs = _expect(d.get("env_installs", {}), dict, "env_installs")
        for k, v in installs.items():
            _expect(v, dict, "env install record")
        return cls(ids, top, snap, overwritten, written, credentials, installs)


def _expect(value: Any, typ: type, what: str) -> Any:
    if not isinstance(value, typ):
        raise ValueError(f"state: {what} must be {typ.__name__}")
    return value


def _str_list(value: Any, what: str) -> list[str]:
    _expect(value, list, what)
    if not all(isinstance(i, str) for i in value):
        raise ValueError(f"state: {what} must be a list of strings")
    return list(value)


def config_key(config_path: Path) -> str:
    return str(Path(config_path).resolve())


@dataclass
class AppState:
    version: int = 1
    profiles: dict[str, Profile] = field(default_factory=dict)
    active_profile: str | None = None
    secret_backend: str | None = None
    last_test: dict[str, Any] | None = None
    configs: dict[str, ConfigOwnership] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profiles": {k: p.to_dict() for k, p in self.profiles.items()},
            "active_profile": self.active_profile,
            "secret_backend": self.secret_backend,
            "last_test": self.last_test,
            "configs": {k: c.to_dict() for k, c in self.configs.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], current_config: Path | None = None) -> AppState:
        version = d.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("state: version must be int")
        profiles = _expect(d.get("profiles", {}), dict, "profiles")
        active = d.get("active_profile")
        backend = d.get("secret_backend")
        for name, val in (("active_profile", active), ("secret_backend", backend)):
            if val is not None and not isinstance(val, str):
                raise ValueError(f"state: {name} must be a string")
        last = d.get("last_test")
        if last is not None:
            _expect(last, dict, "last_test")
        raw_configs = _expect(d.get("configs", {}), dict, "configs")
        configs = {str(k): ConfigOwnership.from_dict(v) for k, v in raw_configs.items()}
        legacy = {
            "managed_provider_ids", "original_top_level", "original_snapshot",
        } & set(d)
        if legacy:
            # Old flat ownership: assign to the current config only if that file exists.
            if current_config is not None and Path(current_config).exists():
                key = config_key(current_config)
                if key not in configs:
                    configs[key] = ConfigOwnership.from_dict(
                        {k: d[k] for k in legacy if d[k] is not None}
                    )
        return cls(
            version=version,
            profiles={str(k): Profile.from_dict(_expect(v, dict, "profile")) for k, v in profiles.items()},
            active_profile=active,
            secret_backend=backend,
            last_test=last,
            configs=configs,
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
        return AppState.from_dict(data, paths.config_path(env))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        bad = path.with_name("state.json.bad")
        try:
            path.replace(bad)
        except OSError:
            pass
        return AppState()


def save_state(state: AppState, env: Mapping[str, str] | None = None) -> None:
    text = json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n"
    path = state_path(env)
    atomic_write_text(path, text)
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)  # may hold a previous env value; keep it private
        except OSError:
            pass
