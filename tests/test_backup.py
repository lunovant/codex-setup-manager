from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_setup.core import backup, paths
from codex_setup.core.errors import CodexSetupError, ConfigParseError
from codex_setup.core.state import AppState


def _cfg(isolated_env, text: str = 'model = "a"\n') -> Path:
    path = paths.config_path(isolated_env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_create_and_list_newest_first(isolated_env) -> None:
    cfg = _cfg(isolated_env)
    first = backup.create_backup(cfg, "one", isolated_env)
    cfg.write_text('model = "b"\n', encoding="utf-8")
    second = backup.create_backup(cfg, "two", isolated_env)
    meta = json.loads(first.with_suffix(".json").read_text())
    assert meta["reason"] == "one" and meta["source"] == str(cfg) and len(meta["sha256"]) == 64
    infos = backup.list_backups(isolated_env)
    assert [i.id for i in infos] == [second.stem, first.stem]
    assert infos[1].reason == "one" and infos[1].size == first.stat().st_size


def test_list_ignores_without_sidecar(isolated_env) -> None:
    cfg = _cfg(isolated_env)
    made = backup.create_backup(cfg, "", isolated_env)
    made.with_suffix(".json").unlink()
    assert backup.list_backups(isolated_env) == []
    assert backup.list_backups({"CODEX_SETUP_HOME": str(cfg.parent / "none")}) == []


def test_find(isolated_env) -> None:
    cfg = _cfg(isolated_env)
    made = backup.create_backup(cfg, "x", isolated_env)
    assert backup.find_backup(made.stem, isolated_env).path == made
    assert backup.find_backup(str(made), isolated_env).id == made.stem
    with pytest.raises(CodexSetupError):
        backup.find_backup("nope", isolated_env)


def test_restore_and_dry_run(isolated_env) -> None:
    cfg = _cfg(isolated_env)
    info = backup.find_backup(backup.create_backup(cfg, "", isolated_env).stem, isolated_env)
    cfg.write_text('model = "changed"\n', encoding="utf-8")
    dry = backup.restore_backup(info, cfg, dry_run=True, env=isolated_env)
    assert dry.dry_run and dry.changed and "changed" in dry.diff
    assert cfg.read_text() == 'model = "changed"\n'
    res = backup.restore_backup(info, cfg, env=isolated_env)
    assert res.changed and cfg.read_text() == 'model = "a"\n'
    assert res.backup is not None and 'changed' in res.backup.read_text()


def test_restore_invalid_backup_rejected(isolated_env) -> None:
    cfg = _cfg(isolated_env)
    made = backup.create_backup(cfg, "", isolated_env)
    made.write_text("[broken", encoding="utf-8")
    info = backup.find_backup(made.stem, isolated_env)
    with pytest.raises(ConfigParseError):
        backup.restore_backup(info, cfg, env=isolated_env)
    assert cfg.read_text() == 'model = "a"\n'


def test_original_snapshot_once(isolated_env) -> None:
    cfg = _cfg(isolated_env)
    state = AppState()
    assert backup.ensure_original_snapshot(cfg, state, isolated_env) is True
    assert state.original_snapshot and Path(state.original_snapshot).exists()
    assert backup.ensure_original_snapshot(cfg, state, isolated_env) is False
    assert len(backup.list_backups(isolated_env)) == 1
    assert backup.list_backups(isolated_env)[0].reason == "original"


def test_original_snapshot_missing_file(isolated_env) -> None:
    state = AppState()
    missing = paths.config_path(isolated_env)
    assert backup.ensure_original_snapshot(missing, state, isolated_env) is True
    assert state.original_snapshot == ""
    assert backup.ensure_original_snapshot(missing, state, isolated_env) is False
