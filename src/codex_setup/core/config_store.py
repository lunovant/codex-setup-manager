"""Load, validate, back up and atomically write Codex config.toml."""

from __future__ import annotations

import difflib
import os
import re
import stat
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError
from tomlkit.toml_document import TOMLDocument

from codex_setup.core.errors import ConfigParseError, ConfigWriteError


@dataclass
class LoadedConfig:
    path: Path
    doc: TOMLDocument
    original_text: str  # "" when the file did not exist
    existed: bool


@dataclass
class SaveResult:
    changed: bool
    diff: str
    backup: Path | None
    dry_run: bool
    # (i18n key, params) hints for the presentation layer, e.g. fields left untouched
    notes: list[tuple[str, dict[str, str]]] = field(default_factory=list)


_TOMLLIB_POS = re.compile(r"\(at line (\d+), column (\d+)\)")


def _parse_error(exc: Exception, path: Path | None) -> ConfigParseError:
    line = getattr(exc, "line", None)
    col = getattr(exc, "col", None)
    if line is None:
        m = _TOMLLIB_POS.search(str(exc))
        if m:
            line, col = int(m.group(1)), int(m.group(2))
    where = f" (line {line}, column {col})" if line is not None else ""
    name = f"{path}: " if path else ""
    return ConfigParseError(f"{name}invalid TOML{where}: {exc}", path=path, line=line, col=col)


def load_config(path: Path) -> LoadedConfig:
    path = Path(path)
    if not path.exists():
        return LoadedConfig(path, tomlkit.document(), "", False)
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigParseError(f"{path}: not valid UTF-8: {exc}", path=path) from exc
    except OSError as exc:
        raise ConfigParseError(f"{path}: cannot read: {exc}", path=path) from exc
    validate_text(text, path)
    try:
        doc = tomlkit.parse(text)
    except TOMLKitError as exc:
        raise _parse_error(exc, path) from exc
    return LoadedConfig(path, doc, text, True)


def render(doc: TOMLDocument) -> str:
    return tomlkit.dumps(doc)


def validate_text(text: str, path: Path | None = None) -> None:
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise _parse_error(exc, path) from exc


def diff_text(old: str, new: str, path: Path) -> str:
    if old == new:
        return ""
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"{path} (current)",
        tofile=f"{path} (new)",
    )
    return "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in lines
    )


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        if os.name == "posix":
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        tmp_name = None
    except OSError as exc:
        raise ConfigWriteError(f"Cannot write {path}: {exc}", path=path) from exc
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _match_line_endings(original: str, new: str) -> str:
    """Keep CRLF files CRLF even though tomlkit adds bare LF for new lines."""
    if "\r\n" in original and "\n" not in original.replace("\r\n", ""):
        return new.replace("\r\n", "\n").replace("\n", "\r\n")
    return new


def _read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        return "\0unreadable"


def _rollback(loaded: LoadedConfig, written: str | None = None) -> None:
    """Restore the original text, but only if the disk still holds what we wrote."""
    path = loaded.path
    if written is not None and _read_text_or_none(path) != written:
        return
    try:
        if loaded.existed:
            atomic_write_text(path, loaded.original_text)
        elif path.exists():
            path.unlink()
    except (OSError, ConfigWriteError):
        pass


def save_config(
    loaded: LoadedConfig,
    *,
    dry_run: bool = False,
    reason: str = "",
    env: Mapping[str, str] | None = None,
) -> SaveResult:
    from codex_setup.core import backup  # local import: backup imports this module

    new_text = _match_line_endings(loaded.original_text, render(loaded.doc))
    validate_text(new_text, loaded.path)
    if loaded.existed and new_text == loaded.original_text:
        return SaveResult(False, "", None, dry_run)
    if not loaded.existed and not new_text:
        return SaveResult(False, "", None, dry_run)
    diff = diff_text(loaded.original_text, new_text, loaded.path)
    if dry_run:
        return SaveResult(True, diff, None, True)

    backup_path: Path | None = None
    if loaded.existed:
        try:
            backup_path = backup.create_backup(loaded.path, reason, env)
        except OSError as exc:
            raise ConfigWriteError(f"Cannot create backup: {exc}", path=loaded.path) from exc

    current = _read_text_or_none(loaded.path)
    if current != (loaded.original_text if loaded.existed else None):
        raise ConfigWriteError(
            "config.toml changed on disk since it was loaded; reload and try again",
            path=loaded.path,
        )
    on_disk = new_text
    try:
        atomic_write_text(loaded.path, new_text)
        written = on_disk = loaded.path.read_bytes().decode("utf-8")
        validate_text(written, loaded.path)
        if written != new_text:
            raise ConfigWriteError("Written file differs from expected content", loaded.path)
    except (ConfigWriteError, ConfigParseError, OSError, UnicodeDecodeError) as exc:
        _rollback(loaded, on_disk)
        if isinstance(exc, ConfigWriteError):
            raise
        raise ConfigWriteError(
            f"Verification after write failed, original restored: {exc}", path=loaded.path
        ) from exc
    return SaveResult(True, diff, backup_path, False)
