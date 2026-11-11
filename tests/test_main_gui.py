from __future__ import annotations

import io

import pytest

from codex_setup import main as cli
from codex_setup.app import SetupService
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.secrets import SecretStore


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict:
    svc = SetupService(secret_store=SecretStore(backend="session"))
    svc._platform = PlatformInfo("macos", "25", "arm64")
    svc._install = CodexInstall(None, None, False, False, None, None, "n/a")
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    rec: dict = {"gui": [], "tui": 0}
    monkeypatch.setattr(cli, "run_gui", lambda lang=None: rec["gui"].append(lang) or 0)
    from codex_setup.ui import tui

    monkeypatch.setattr(tui, "run", lambda *a, **k: rec.__setitem__("tui", rec["tui"] + 1) or 0)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    return rec


def test_no_args_runs_gui_when_available(calls, monkeypatch):
    monkeypatch.setattr(cli, "gui_available", lambda: (True, "cocoa"))
    assert cli.main([]) == 0
    assert calls["gui"] == [None] and calls["tui"] == 0


def test_no_args_falls_back_to_tui_path(calls, monkeypatch, capsys):
    monkeypatch.setattr(cli, "gui_available", lambda: (False, "nope"))
    assert cli.main(["--lang", "en"]) == 0
    assert calls["gui"] == []
    assert "codex-setup --help" in capsys.readouterr().out  # non-TTY hint


def test_tui_flag_skips_gui(calls, monkeypatch):
    monkeypatch.setattr(cli, "gui_available", lambda: (True, "cocoa"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    class TTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("sys.stdin", TTY(""))
    monkeypatch.setattr("sys.stdout", TTY())
    assert cli.main(["--tui"]) == 0
    assert calls["gui"] == [] and calls["tui"] == 1


def test_gui_flag_forces_gui_and_passes_lang(calls, monkeypatch):
    monkeypatch.setattr(cli, "gui_available", lambda: (True, "cocoa"))
    assert cli.main(["--gui", "--lang", "vi"]) == 0
    assert calls["gui"] == ["vi"]


def test_gui_flag_errors_when_unavailable(calls, monkeypatch, capsys):
    monkeypatch.setattr(cli, "gui_available", lambda: (False, "no gtk"))
    assert cli.main(["--gui", "--lang", "en"]) == 1
    assert calls["gui"] == [] and "no gtk" in capsys.readouterr().err


def test_gui_and_tui_conflict(calls):
    assert cli.main(["--gui", "--tui"]) == 2


def test_subcommand_unaffected_by_gui(calls, monkeypatch):
    monkeypatch.setattr(cli, "gui_available", lambda: (True, "cocoa"))
    assert cli.main(["--lang", "en", "status"]) == 0
    assert calls["gui"] == []


def test_selftest_ok_and_unavailable(calls, monkeypatch, capsys):
    monkeypatch.setattr(cli, "gui_available", lambda: (True, "cocoa"))
    assert cli.main(["gui-selftest"]) == 0
    assert capsys.readouterr().out.strip() == "gui ok cocoa"
    monkeypatch.setattr(cli, "gui_available", lambda: (False, "no gtk"))
    assert cli.main(["gui-selftest"]) == 1
    assert capsys.readouterr().out.strip() == "gui unavailable: no gtk"
    assert calls["gui"] == []


def test_gui_available_never_opens_window():
    from codex_setup.gui.app import gui_available

    ok, info = gui_available()
    assert isinstance(ok, bool) and isinstance(info, str) and info
