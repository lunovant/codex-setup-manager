"""Config backups: create, list, find, restore, original snapshot."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from codex_setup.core import paths
from codex_setup.core.config_store import (
    SaveResult,
    atomic_write_text,
    diff_text,
    validate_text,
)
from codex_setup.core.errors import CodexSetupError, ConfigParseError
from codex_setup.core.state import AppState


@dataclass
class BackupInfo:
    id: str
    path: Path
    created: str
    reason: str
    source: str
    sha256: str
    size: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_backup(path: Path, reason: str = "", env: Mapping[str, str] | None = None) -> Path:
    path = Path(path)
    directory = paths.backups_dir(env)
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    stem = f"config-{now.strftime('%Y%m%d-%H%M%S-%f')}"
    dest = directory / f"{stem}.toml"
    n = 1
    while dest.exists():  # extremely unlikely, keep ids unique anyway
        dest = directory / f"{stem}-{n}.toml"
        n += 1
    shutil.copy2(path, dest)
    meta = {
        "source": str(path),
        "created": now.astimezone().isoformat(timespec="seconds"),
        "reason": reason,
        "sha256": _sha256(dest),
    }
    dest.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return dest


def _read_info(toml_path: Path) -> BackupInfo | None:
    sidecar = toml_path.with_suffix(".json")
    if not toml_path.is_file() or not sidecar.is_file():
        return None
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        return BackupInfo(
            id=toml_path.stem,
            path=toml_path,
            created=str(meta.get("created", "")),
            reason=str(meta.get("reason", "")),
            source=str(meta.get("source", "")),
            sha256=str(meta.get("sha256", "")),
            size=toml_path.stat().st_size,
        )
    except (OSError, ValueError):
        return None


def list_backups(env: Mapping[str, str] | None = None) -> list[BackupInfo]:
    directory = paths.backups_dir(env)
    if not directory.is_dir():
        return []
    infos = [i for p in directory.glob("config-*.toml") if (i := _read_info(p))]
    return sorted(infos, key=lambda i: i.id, reverse=True)


def find_backup(id_or_path: str, env: Mapping[str, str] | None = None) -> BackupInfo:
    candidate = Path(id_or_path)
    if candidate.suffix == ".toml" and candidate.is_file():
        info = _read_info(candidate)
        if info:
            return info
    for info in list_backups(env):
        if info.id == id_or_path or info.path == candidate:
            return info
    raise CodexSetupError(f"Backup not found: {id_or_path}")


def restore_backup(
    info: BackupInfo,
    target: Path,
    *,
    dry_run: bool = False,
    env: Mapping[str, str] | None = None,
) -> SaveResult:
    target = Path(target)
    try:
        text = info.path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigParseError(f"Cannot read backup {info.id}: {exc}", path=info.path) from exc
    validate_text(text, info.path)
    current = target.read_bytes().decode("utf-8", errors="replace") if target.exists() else ""
    diff = diff_text(current, text, target)
    if target.exists() and current == text:
        return SaveResult(False, "", None, dry_run)
    if dry_run:
        return SaveResult(True, diff, None, True)
    safety = create_backup(target, f"before restore {info.id}", env) if target.exists() else None
    atomic_write_text(target, text)
    return SaveResult(True, diff, safety, False)


def ensure_original_snapshot(
    path: Path, state: AppState, env: Mapping[str, str] | None = None
) -> bool:
    if state.original_snapshot is not None:
        return False
    path = Path(path)
    if not path.exists():
        state.original_snapshot = ""
        return True
    state.original_snapshot = str(create_backup(path, "original", env))
    return True
