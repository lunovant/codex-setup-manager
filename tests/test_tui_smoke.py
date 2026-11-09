from __future__ import annotations

import tomllib

from rich.console import Console
from rich.prompt import Confirm, Prompt

from codex_setup.app import SetupService
from codex_setup.core import paths
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.secrets import SecretStore
from codex_setup.ui import tui
from codex_setup.ui.i18n import set_lang

KEY = "sk-tui-SECRET-9876543210"


def test_quick_setup_then_exit(monkeypatch):
    set_lang("en")
    svc = SetupService(secret_store=SecretStore(backend="session"))
    svc._platform = PlatformInfo("macos", "25", "arm64")
    svc._install = CodexInstall(None, None, False, False, None, None, "n/a")
    answers = iter(["1", "", "", "session", "0"])  # menu 1, url default, model default, backend, exit

    def fake_ask(*args, **kwargs):
        value = next(answers)
        return value if value != "" else kwargs.get("default", "")

    monkeypatch.setattr(Prompt, "ask", fake_ask)
    monkeypatch.setattr(Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: KEY)
    console = Console(record=True, width=120, force_terminal=False)
    assert tui.run(svc, console=console) == 0
    data = tomllib.loads(paths.config_path().read_text())
    assert data["model_provider"] == "lunovant" and data["model"] == "gpt-6.1-sol"
    assert svc.secret_store().get("LUNOVANT_API_KEY") == KEY
    out = console.export_text()
    assert KEY not in out
    assert "Quick Setup" in out and "Windows Sandbox" not in out
