"""Window creation for the pywebview GUI. Importing this module never opens a window."""

from __future__ import annotations

import ctypes
import importlib.util
import sys
from pathlib import Path

from codex_setup.gui.api import GuiApi

TITLE = "Codex Setup Manager"


def web_dir() -> Path:
    """Packaged ``web`` directory; also valid in a PyInstaller bundle (sys._MEIPASS)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        frozen = Path(meipass) / "codex_setup" / "gui" / "web"
        if frozen.is_dir():
            return frozen
    return Path(__file__).resolve().parent / "web"


def index_path() -> Path:
    return web_dir() / "index.html"


def _has(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def gui_available() -> tuple[bool, str]:
    """(ok, backend-or-reason). Never opens a window."""
    try:
        import webview  # noqa: F401
    except Exception as exc:
        return False, f"pywebview is not importable ({exc.__class__.__name__}: {exc})"
    if not index_path().is_file():
        return False, f"packaged UI files are missing: {index_path()}"
    if sys.platform.startswith("linux"):
        if _has("gi"):
            return True, "gtk"
        if _has("qtpy") and (_has("PyQt5") or _has("PyQt6") or _has("PySide2") or _has("PySide6")):
            return True, "qt"
        return False, "no GTK (PyGObject + WebKit2) or Qt (qtpy + PyQt/PySide) backend found"
    if sys.platform == "darwin":
        return True, "cocoa"
    if sys.platform.startswith("win"):
        return True, "edgechromium"
    return True, "default"


def hide_console_if_detached() -> None:
    """Windows only: free the console when started from Explorer (no parent console)."""
    if not sys.platform.startswith("win"):
        return
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        procs = (ctypes.c_uint * 2)()
        if kernel32.GetConsoleProcessList(procs, 2) == 1:
            kernel32.FreeConsole()
    except Exception:
        pass


def run_gui(lang: str | None = None) -> int:
    import webview

    hide_console_if_detached()
    api = GuiApi(lang=lang)
    webview.create_window(
        TITLE,
        url=str(index_path()),
        js_api=api,
        width=980,
        height=720,
        min_size=(760, 560),
    )
    webview.start()
    return 0
