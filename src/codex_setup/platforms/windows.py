"""Windows Desktop detection and persistent user environment (winreg, lazy)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

APP_EXE_NAMES = ("Codex.exe", "ChatGPT.exe")
_ENV_SUBKEY = "Environment"


def _local_appdata(env: Mapping[str, str]) -> Path | None:
    value = env.get("LOCALAPPDATA")
    if value:
        return Path(value)
    profile = env.get("USERPROFILE")
    return Path(profile) / "AppData" / "Local" if profile else None


def detect_desktop(
    *, env: Mapping[str, str], roots: Sequence[Path] | None = None
) -> dict[str, Any]:
    """Look for app executables under Programs\\* and WindowsApps aliases."""
    if roots is None:
        base = _local_appdata(env)
        roots = [base] if base else []
    for base in roots:
        base = Path(base)
        programs = base / "Programs"
        if programs.is_dir():
            try:
                children = sorted(p for p in programs.iterdir() if p.is_dir())
            except OSError:
                children = []
            for child in children:
                for name in APP_EXE_NAMES:
                    for exe in (child / name, child / "app" / name):
                        if exe.is_file():
                            return _found(exe)
        for name in APP_EXE_NAMES:
            alias = base / "Microsoft" / "WindowsApps" / name
            try:
                if alias.exists() or alias.is_symlink():
                    return _found(alias)
            except OSError:
                continue
    return {
        "supported": True,
        "installed": False,
        "path": None,
        "executable": None,
        "note": "Codex Desktop not detected (it may still be installed as a Microsoft Store app).",
    }


def _found(exe: Path) -> dict[str, Any]:
    return {
        "supported": True,
        "installed": True,
        "path": str(exe),
        "executable": str(exe),
        "note": f"Codex Desktop found at {exe}.",
    }


# -- persistent user environment ------------------------------------------
def _import_winreg() -> Any:
    import winreg  # type: ignore[import-not-found]

    return winreg


def get_user_env_typed(name: str) -> tuple[str, int] | None:
    """Current (value, registry type) or None when the value is absent."""
    winreg = _import_winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_SUBKEY, 0, winreg.KEY_READ) as key:
            value, reg_type = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None
    return str(value), int(reg_type)


def get_user_env(name: str) -> str | None:
    typed = get_user_env_typed(name)
    return None if typed is None else typed[0]


def set_user_env(name: str, value: str, reg_type: int | None = None) -> None:
    winreg = _import_winreg()
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, _ENV_SUBKEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ if reg_type is None else reg_type, value)
    broadcast_env_change()


def remove_user_env(name: str) -> bool:
    winreg = _import_winreg()
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _ENV_SUBKEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        return False
    broadcast_env_change()
    return True


def broadcast_env_change() -> None:
    """Tell running apps the environment changed (best effort)."""
    try:
        import ctypes
        from ctypes import wintypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        send = ctypes.windll.user32.SendMessageTimeoutW  # type: ignore[attr-defined]
        send.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            ctypes.c_wchar_p,  # LPARAM carrying a string pointer
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        send.restype = wintypes.LPARAM
        result = ctypes.c_size_t()
        send(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            ctypes.byref(result),
        )
    except Exception:
        pass
