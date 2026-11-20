from __future__ import annotations

import os
import shutil
from pathlib import Path

from codex_setup.core import claude_config
from codex_setup.core.claude_config import find_claude_cli
from codex_setup.gui import strings as gui_strings
from tests.test_gui_api import _make


def _exe(path: Path, mode: int = 0o755) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(mode)
    return path


def _no_which(monkeypatch, result=None, tmp=None):
    monkeypatch.setattr(shutil, "which", lambda name: result)
    # Isolate from real system installs: map the absolute candidates into a fake root.
    root = (tmp or Path(os.devnull).parent) / "sysroot"
    monkeypatch.setattr(
        claude_config,
        "_SYSTEM_CLAUDE_PATHS",
        (root / "opt" / "homebrew" / "bin" / "claude", root / "usr" / "local" / "bin" / "claude"),
    )


def test_which_hit_wins(monkeypatch, tmp_path):
    _exe(tmp_path / ".local" / "bin" / "claude")
    _no_which(monkeypatch, "/usr/bin/claude")
    assert find_claude_cli("macos", tmp_path, {}) == "/usr/bin/claude"


def test_fallback_order(monkeypatch, tmp_path):
    _no_which(monkeypatch, tmp=tmp_path)
    assert find_claude_cli("linux", tmp_path, {}) is None
    bun = _exe(tmp_path / ".bun" / "bin" / "claude")
    assert find_claude_cli("linux", tmp_path, {}) == str(bun)
    npm = _exe(tmp_path / ".npm-global" / "bin" / "claude")
    assert find_claude_cli("linux", tmp_path, {}) == str(npm)
    usr = _exe(tmp_path / "sysroot" / "usr" / "local" / "bin" / "claude")
    assert find_claude_cli("linux", tmp_path, {}) == str(usr)
    brew = _exe(tmp_path / "sysroot" / "opt" / "homebrew" / "bin" / "claude")
    assert find_claude_cli("linux", tmp_path, {}) == str(brew)
    local = _exe(tmp_path / ".claude" / "local" / "claude")
    assert find_claude_cli("linux", tmp_path, {}) == str(local)
    first = _exe(tmp_path / ".local" / "bin" / "claude")
    assert find_claude_cli("linux", tmp_path, {}) == str(first)


def test_non_executable_and_dirs_ignored(monkeypatch, tmp_path):
    _no_which(monkeypatch, tmp=tmp_path)
    _exe(tmp_path / ".local" / "bin" / "claude", 0o644)
    (tmp_path / ".claude" / "local" / "claude").mkdir(parents=True)
    ok = _exe(tmp_path / ".bun" / "bin" / "claude")
    assert find_claude_cli("macos", tmp_path, {}) == str(ok)


def test_windows_candidates(monkeypatch, tmp_path):
    _no_which(monkeypatch, tmp=tmp_path)
    prof, appdata = tmp_path / "prof", tmp_path / "appdata"
    env = {"USERPROFILE": str(prof), "APPDATA": str(appdata)}
    assert find_claude_cli("windows", tmp_path, env) is None
    cmd = _exe(appdata / "npm" / "claude.cmd", 0o644)
    assert find_claude_cli("windows", tmp_path, env) == str(cmd)
    exe = _exe(prof / ".local" / "bin" / "claude.exe", 0o644)
    assert find_claude_cli("windows", tmp_path, env) == str(exe)
    assert find_claude_cli("windows", tmp_path, {}) is None


def test_claude_status_uses_finder(monkeypatch):
    gui = _make()
    monkeypatch.setattr(claude_config, "find_claude_cli", lambda s, h, e: "/x/claude")
    assert gui._claude_status()["cli_path"] == "/x/claude"


def test_howto_strings_parity():
    en = {k for k in gui_strings.EN if k.startswith("g_howto_")}
    vi = {k for k in gui_strings.VI if k.startswith("g_howto_")}
    assert en == vi and "g_howto_jb_t" in en
