"""Opt-in POSIX shell rc marker block holding the API key (plaintext!)."""

from __future__ import annotations

import os
import re
import shutil
import time
from collections.abc import Mapping
from pathlib import Path

from codex_setup.core.config_store import atomic_write_text
from codex_setup.core.errors import ValidationError

START = "# >>> codex-setup-manager >>>"
END = "# <<< codex-setup-manager <<<"
PLAINTEXT_WARNING = "WARNING: this stores the API key in plaintext in your shell startup file."
_ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def choose_rc(shell: str | None, home: Path) -> Path:
    name = Path(shell or "").name
    if name == "zsh":
        return home / ".zshrc"
    if name == "bash":
        return home / ".bashrc"
    return home / ".profile"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _read(rc_path: Path) -> str:
    try:
        return rc_path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return ""


def _block_re() -> re.Pattern[str]:
    return re.compile(
        rf"(?:^|(?<=\n)){re.escape(START)}\n.*?{re.escape(END)}\n?", re.DOTALL
    )


def has_block(rc_path: Path) -> bool:
    text = _read(rc_path)
    return START in text and END in text


def _backup(rc_path: Path) -> Path | None:
    if not rc_path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = rc_path.with_name(f"{rc_path.name}.codex-setup-backup-{stamp}")
    n = 0
    while dest.exists():
        n += 1
        dest = rc_path.with_name(f"{rc_path.name}.codex-setup-backup-{stamp}-{n}")
    shutil.copy2(rc_path, dest)
    return dest


def _write_keep_mode(rc_path: Path, text: str) -> None:
    mode = None
    if rc_path.exists():
        mode = rc_path.stat().st_mode & 0o7777
    atomic_write_text(rc_path, text)
    if mode is not None:
        os.chmod(rc_path, mode)


def _without_block(text: str) -> str:
    return _block_re().sub("", text)


def install_block(rc_path: Path, env_key: str, value: str) -> Path | None:
    """Add/replace the marker block. Returns the backup path (None if no file existed)."""
    if not _ENV_KEY_RE.match(env_key):
        raise ValidationError(f"Invalid environment variable name: {env_key}")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ValidationError("Secret value must be a single line.")
    text = _read(rc_path)
    backup = _backup(rc_path)
    base = _without_block(text)
    if base and not base.endswith("\n"):
        base += "\n"
    block = f"{START}\nexport {env_key}={shell_quote(value)}\n{END}\n"
    _write_keep_mode(rc_path, base + block)
    if backup is None:
        os.chmod(rc_path, 0o600)
    return backup


def remove_block(rc_path: Path, env_key: str | None = None) -> bool:
    """Remove the marker block. Returns True if something was removed."""
    if not rc_path.exists():
        return False
    text = _read(rc_path)
    new = _without_block(text)
    if new == text:
        return False
    _backup(rc_path)
    _write_keep_mode(rc_path, new)
    return True
