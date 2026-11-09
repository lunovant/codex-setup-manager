"""Resolve Codex and app directories. Nothing here creates directories."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

APP_DIR_NAME = "codex-setup-manager"


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _system(system: str | None) -> str:
    s = (system or sys.platform).lower()
    if s.startswith("win"):
        return "windows"
    if s in ("darwin", "macos"):
        return "macos"
    return "linux"


def _home(env: Mapping[str, str], system: str | None = None) -> Path:
    """HOME / USERPROFILE from the env mapping first, then Path.home()."""
    keys = ("USERPROFILE", "HOME") if _system(system) == "windows" else ("HOME", "USERPROFILE")
    for key in keys:
        value = env.get(key)
        if value:
            return Path(value)
    return Path.home()


def _expand(value: str, env: Mapping[str, str], system: str | None) -> Path:
    if value == "~" or value.startswith(("~/", "~\\")):
        return _home(env, system) / value[2:] if len(value) > 1 else _home(env, system)
    return Path(value)


def codex_home(env: Mapping[str, str] | None = None, *, system: str | None = None) -> Path:
    e = _env(env)
    value = e.get("CODEX_HOME")
    if value and value.strip():
        return _expand(value.strip(), e, system)
    return _home(e, system) / ".codex"


def config_path(env: Mapping[str, str] | None = None, *, system: str | None = None) -> Path:
    return codex_home(env, system=system) / "config.toml"


def profile_config_path(
    name: str, env: Mapping[str, str] | None = None, *, system: str | None = None
) -> Path:
    return codex_home(env, system=system) / f"{name}.config.toml"


def app_state_dir(env: Mapping[str, str] | None = None, *, system: str | None = None) -> Path:
    e = _env(env)
    override = e.get("CODEX_SETUP_HOME")
    if override and override.strip():
        return _expand(override.strip(), e, system)
    sysname = _system(system)
    home = _home(e, system)
    if sysname == "windows":
        appdata = e.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / APP_DIR_NAME
    if sysname == "macos":
        return home / "Library" / "Application Support" / APP_DIR_NAME
    xdg = e.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else home / ".config"
    return base / APP_DIR_NAME


def backups_dir(env: Mapping[str, str] | None = None, *, system: str | None = None) -> Path:
    return app_state_dir(env, system=system) / "backups"
