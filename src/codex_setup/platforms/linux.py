"""Linux Desktop detection, distro info and the support matrix."""

from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

SUPPORTED = {
    "ubuntu": ("24.04", "26.04"),
    "debian": ("13",),
    "fedora": ("43", "44"),
}


def parse_os_release(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        try:
            parts = shlex.split(value)
            out[key.strip()] = parts[0] if parts else ""
        except ValueError:
            out[key.strip()] = value.strip("\"'")
    return out


def read_distro(os_release: str | Path | None = None) -> tuple[str | None, str | None]:
    text: str | None
    if isinstance(os_release, Path):
        try:
            text = os_release.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = None
    elif isinstance(os_release, str):
        text = os_release
    else:
        text = None
        for candidate in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
                break
            except OSError:
                continue
    if not text:
        return None, None
    data = parse_os_release(text)
    return (data.get("ID") or None), (data.get("VERSION_ID") or None)


def support_status(distro_id: str | None, distro_version: str | None) -> tuple[bool, str]:
    did = (distro_id or "").lower()
    ver = distro_version or ""
    if did == "ubuntu" and ver == "22.04":
        return False, "Ubuntu 22.04 has no official Codex Desktop app. Use the Codex CLI instead."
    if did in ("arch", "archlinux", "manjaro", "endeavouros"):
        return True, "Arch Linux is supported for the Codex Desktop preview."
    if did in SUPPORTED and ver in SUPPORTED[did]:
        return True, f"{did} {ver} is supported for the Codex Desktop preview."
    label = f"{distro_id or 'unknown'} {ver}".strip()
    return False, f"{label} is not officially supported for Codex Desktop. Use the Codex CLI."


def detect_desktop(platform: Any, *, which: Callable[[str], str | None]) -> dict[str, Any]:
    supported, note = support_status(platform.distro_id, platform.distro_version)
    exe = which("chatgpt")
    if exe:
        return {
            "supported": supported,
            "installed": True,
            "path": exe,
            "executable": exe,
            "note": f"Found `chatgpt` at {exe}." + ("" if supported else f" {note}"),
        }
    return {
        "supported": supported,
        "installed": False,
        "path": None,
        "executable": None,
        "note": note + ("" if not supported else " `chatgpt` was not found on PATH."),
    }
