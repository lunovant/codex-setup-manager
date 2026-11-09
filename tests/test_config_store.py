from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from codex_setup.core import backup, codex_config as cc, config_store as cs
from codex_setup.core.errors import ConfigParseError, ConfigWriteError
from codex_setup.providers.catalog import LUNOVANT


def _edit(loaded: cs.LoadedConfig) -> None:
    cc.upsert_provider(loaded.doc, LUNOVANT)
    cc.set_active(loaded.doc, "lunovant", "gpt-6.1-sol")


def test_invalid_toml_has_line(make_config) -> None:
    path = make_config("invalid.toml")
    with pytest.raises(ConfigParseError) as err:
        cs.load_config(path)
    assert err.value.line == 2 and err.value.path == path


def test_bad_utf8(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    path.write_bytes(b"model = '\xff\xfe'\n")
    with pytest.raises(ConfigParseError):
        cs.load_config(path)


def test_missing_file(tmp_path: Path) -> None:
    loaded = cs.load_config(tmp_path / "nope" / "config.toml")
    assert not loaded.existed and loaded.original_text == ""


def test_dry_run_untouched(make_config, isolated_env) -> None:
    path = make_config("macos_config.toml")
    before = path.read_bytes()
    loaded = cs.load_config(path)
    _edit(loaded)
    res = cs.save_config(loaded, dry_run=True, env=isolated_env)
    assert res.dry_run and res.changed and res.backup is None
    assert "+model_provider" in res.diff and "lunovant" in res.diff
    assert path.read_bytes() == before
    assert backup.list_backups(isolated_env) == []


def test_dry_run_missing_file_not_created(tmp_path: Path, isolated_env) -> None:
    loaded = cs.load_config(tmp_path / "d" / "config.toml")
    _edit(loaded)
    res = cs.save_config(loaded, dry_run=True, env=isolated_env)
    assert res.changed and not (tmp_path / "d").exists()


def test_save_creates_backup_and_writes(make_config, isolated_env) -> None:
    path = make_config("linux_config.toml")
    before = path.read_text(encoding="utf-8")
    loaded = cs.load_config(path)
    _edit(loaded)
    res = cs.save_config(loaded, reason="setup", env=isolated_env)
    assert res.changed and res.backup and res.backup.read_text(encoding="utf-8") == before
    assert "lunovant" in path.read_text(encoding="utf-8")
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]
    assert backup.list_backups(isolated_env)[0].reason == "setup"


def test_no_change_no_backup(make_config, isolated_env) -> None:
    path = make_config("macos_config.toml")
    res = cs.save_config(cs.load_config(path), env=isolated_env)
    assert not res.changed and res.backup is None
    assert backup.list_backups(isolated_env) == []


def test_crlf_preserved(make_config, isolated_env) -> None:
    path = make_config("windows_config.toml")
    loaded = cs.load_config(path)
    _edit(loaded)
    cs.save_config(loaded, env=isolated_env)
    raw = path.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert b"lunovant" in raw


def test_new_file_created(tmp_path: Path, isolated_env) -> None:
    path = tmp_path / "fresh" / ".codex" / "config.toml"
    loaded = cs.load_config(path)
    _edit(loaded)
    res = cs.save_config(loaded, env=isolated_env)
    assert res.changed and res.backup is None and path.is_file()


def test_file_mode_kept(make_config, isolated_env) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX modes")
    path = make_config("macos_config.toml")
    path.chmod(0o600)
    loaded = cs.load_config(path)
    _edit(loaded)
    cs.save_config(loaded, env=isolated_env)
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions and non-root",
)
def test_permission_error(make_config, isolated_env) -> None:
    path = make_config("macos_config.toml")
    before = path.read_bytes()
    loaded = cs.load_config(path)
    _edit(loaded)
    path.parent.chmod(0o500)
    try:
        with pytest.raises(ConfigWriteError):
            cs.save_config(loaded, env=isolated_env)
    finally:
        path.parent.chmod(0o700)
    assert path.read_bytes() == before
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]


def test_rollback_when_post_validation_fails(make_config, isolated_env, monkeypatch) -> None:
    path = make_config("macos_config.toml")
    before = path.read_bytes()
    loaded = cs.load_config(path)
    _edit(loaded)
    real = cs.validate_text
    calls = {"n": 0}

    def flaky(text: str, p: Path | None = None) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:  # 1st call is pre-write validation
            raise ConfigParseError("boom", path=p)
        real(text, p)

    monkeypatch.setattr(cs, "validate_text", flaky)
    with pytest.raises(ConfigWriteError):
        cs.save_config(loaded, env=isolated_env)
    assert path.read_bytes() == before


def test_rollback_deletes_new_file(tmp_path: Path, isolated_env, monkeypatch) -> None:
    path = tmp_path / "n" / "config.toml"
    loaded = cs.load_config(path)
    _edit(loaded)
    real = cs.validate_text
    calls = {"n": 0}

    def flaky(text: str, p: Path | None = None) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise ConfigParseError("boom", path=p)
        real(text, p)

    monkeypatch.setattr(cs, "validate_text", flaky)
    with pytest.raises(ConfigWriteError):
        cs.save_config(loaded, env=isolated_env)
    assert not path.exists()


def test_os_replace_failure_leaves_original(make_config, isolated_env, monkeypatch) -> None:
    path = make_config("linux_config.toml")
    before = path.read_bytes()
    loaded = cs.load_config(path)
    _edit(loaded)

    def fail(*a, **k):
        raise PermissionError("denied")

    with monkeypatch.context() as m:  # never monkeypatch.undo(): it would drop env isolation
        m.setattr(os, "replace", fail)
        with pytest.raises(ConfigWriteError):
            cs.save_config(loaded, env=isolated_env)
    assert path.read_bytes() == before
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]


def test_invalid_doc_rejected_before_write(make_config, isolated_env, monkeypatch) -> None:
    path = make_config("macos_config.toml")
    before = path.read_bytes()
    loaded = cs.load_config(path)
    monkeypatch.setattr(cs, "render", lambda doc: "[broken")
    with pytest.raises(ConfigParseError):
        cs.save_config(loaded, env=isolated_env)
    assert path.read_bytes() == before
    assert backup.list_backups(isolated_env) == []


def test_diff_text() -> None:
    assert cs.diff_text("a\n", "a\n", Path("x")) == ""
    assert "-a" in cs.diff_text("a\n", "b\n", Path("x"))
