"""Platform and Codex install detection (all I/O injectable)."""

from __future__ import annotations

import os
import platform as _platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_VERSION_RE = None


@dataclass
class PlatformInfo:
    system: Literal["windows", "macos", "linux"]
    release: str
    machine: str
    distro_id: str | None = None
    distro_version: str | None = None


@dataclass
class CodexInstall:
    cli_path: str | None
    cli_version: str | None
    desktop_supported: bool
    desktop_installed: bool
    desktop_path: str | None
    desktop_executable: str | None
    desktop_note: str


def detect_platform(
    *, system: str | None = None, os_release: str | Path | None = None
) -> PlatformInfo:
    raw = (system or sys.platform).lower()
    if raw.startswith("win"):
        name: Literal["windows", "macos", "linux"] = "windows"
    elif raw in ("darwin", "macos"):
        name = "macos"
    else:
        name = "linux"
    info = PlatformInfo(system=name, release=_platform.release(), machine=_platform.machine())
    if name == "linux":
        from codex_setup.platforms import linux

        info.distro_id, info.distro_version = linux.read_distro(os_release)
    return info


def parse_cli_version(output: str) -> str | None:
    import re

    m = re.search(r"(\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.\-+]+)?)", output or "")
    return m.group(1) if m else None


def cli_version(
    cli_path: str, run: Callable[..., Any] = subprocess.run, env: Mapping[str, str] | None = None
) -> str | None:
    try:
        proc = run(
            [cli_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            **({"env": dict(env)} if env is not None else {}),
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    return parse_cli_version((proc.stdout or "") + " " + (proc.stderr or ""))


def detect_codex(
    platform: PlatformInfo,
    *,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., Any] = subprocess.run,
    env: Mapping[str, str] | None = None,
    roots: Sequence[Path] | None = None,
) -> CodexInstall:
    e = os.environ if env is None else env
    cli_path = which("codex")
    version = cli_version(cli_path, run) if cli_path else None
    if platform.system == "macos":
        from codex_setup.platforms import macos

        desk = macos.detect_desktop(env=e, roots=roots)
    elif platform.system == "windows":
        from codex_setup.platforms import windows

        desk = windows.detect_desktop(env=e, roots=roots)
    else:
        from codex_setup.platforms import linux

        desk = linux.detect_desktop(platform, which=which)
    return CodexInstall(
        cli_path=cli_path,
        cli_version=version,
        desktop_supported=desk["supported"],
        desktop_installed=desk["installed"],
        desktop_path=desk.get("path"),
        desktop_executable=desk.get("executable"),
        desktop_note=desk["note"],
    )
