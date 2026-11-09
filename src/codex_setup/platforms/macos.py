"""macOS Desktop app detection via bundle identifier."""

from __future__ import annotations

import plistlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

BUNDLE_ID = "com.openai.codex"
APP_NAMES = ("ChatGPT.app", "Codex.app")


def default_roots(env: Mapping[str, str]) -> list[Path]:
    home = Path(env.get("HOME") or Path.home())
    return [Path("/Applications"), home / "Applications"]


def _read_plist(app: Path) -> dict[str, Any] | None:
    try:
        with (app / "Contents" / "Info.plist").open("rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError, Exception):
        return None
    return data if isinstance(data, dict) else None


def detect_desktop(
    *, env: Mapping[str, str], roots: Sequence[Path] | None = None
) -> dict[str, Any]:
    for root in roots if roots is not None else default_roots(env):
        for name in APP_NAMES:
            app = Path(root) / name
            info = _read_plist(app)
            if not info or info.get("CFBundleIdentifier") != BUNDLE_ID:
                continue
            exe_name = info.get("CFBundleExecutable")
            exe = app / "Contents" / "MacOS" / str(exe_name) if exe_name else None
            if exe is None or not exe.exists():
                return {
                    "supported": True,
                    "installed": True,
                    "path": str(app),
                    "executable": None,
                    "note": f"Found {app} but its executable could not be resolved.",
                }
            return {
                "supported": True,
                "installed": True,
                "path": str(app),
                "executable": str(exe),
                "note": f"Codex Desktop found at {app}.",
            }
    return {
        "supported": True,
        "installed": False,
        "path": None,
        "executable": None,
        "note": "Codex Desktop app not found in /Applications or ~/Applications.",
    }
