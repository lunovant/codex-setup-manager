"""Start Codex with the API key injected through the environment only."""

from __future__ import annotations

import os
import shlex
import shutil
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


def _terminal_command(system: str, which: Callable[[str], str | None]) -> list[str] | None:
    """Prefix that runs the rest of the argv inside a new terminal window (Linux only)."""
    for name, flag in (
        ("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"),
        ("xfce4-terminal", "-x"), ("xterm", "-e"),
    ):
        if which(name):
            return [name, flag]
    return None


def terminal_supported(
    system: str, *, which: Callable[[str], str | None] = shutil.which
) -> bool:
    """Whether :func:`open_terminal` can open a window on this platform."""
    if system in ("macos", "windows"):
        return True
    return _terminal_command(system, which) is not None


def open_terminal(
    system: str,
    argv: list[str],
    *,
    popen: Callable[..., Any] = subprocess.Popen,
    which: Callable[[str], str | None] = shutil.which,
) -> None:
    """Open a new terminal window running ``argv`` (no secrets: the command reads its own
    config file). Raises CodexSetupError where no terminal can be opened."""
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if system == "macos":
        line = " ".join(shlex.quote(a) for a in argv)
        escaped = line.replace("\\", "\\\\").replace('"', '\\"')
        popen(
            ["osascript", "-e", 'tell application "Terminal" to activate',
             "-e", f'tell application "Terminal" to do script "{escaped}"'],
            start_new_session=True, **quiet,
        )
    elif system == "windows":
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        popen(["cmd.exe", "/k", *argv], creationflags=flags)
    else:
        prefix = _terminal_command(system, which)
        if prefix is None:
            raise CodexSetupError("No terminal emulator was found to open a window.")
        popen([*prefix, *argv], start_new_session=True, **quiet)
