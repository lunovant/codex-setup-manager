"""Start Codex with the API key injected through the environment only."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from codex_setup.core.errors import CodexSetupError
from codex_setup.platforms.base import CodexInstall, PlatformInfo


def build_env(base: Mapping[str, str], env_key: str, secret: str) -> dict[str, str]:
    env = dict(base)
    env[env_key] = secret
    return env


def launch_cli(
    args: list[str],
    env_key: str,
    secret: str,
    *,
    codex_path: str,
    run: Callable[..., Any] = subprocess.run,
) -> int:
    env = build_env(os.environ, env_key, secret)
    proc = run([codex_path, *args], env=env)
    return int(proc.returncode)


def launch_desktop(
    install: CodexInstall,
    platform: PlatformInfo,
    env_key: str,
    secret: str,
    *,
    popen: Callable[..., Any] = subprocess.Popen,
) -> None:
    if not install.desktop_supported:
        raise CodexSetupError(f"Codex Desktop is not supported here. {install.desktop_note}")
    if not install.desktop_installed or not install.desktop_executable:
        raise CodexSetupError(
            "Codex Desktop is not installed (or its executable was not found). "
            "Install it first, or launch the CLI instead."
        )
    env = build_env(os.environ, env_key, secret)
    exe = install.desktop_executable
    if platform.system == "macos":
        popen(
            [exe],
            env=env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif platform.system == "windows":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        popen(
            [exe],
            env=env,
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        popen(
            [exe],
            env=env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
