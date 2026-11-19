"""Claude Code line: pure helpers for ``~/.claude/settings.json`` and the Lunovant profile file.

Nothing here talks to the network or to the app state. The only files ever *written* are
``settings.json`` and ``lunovant-settings.json``. ``.claude.json`` is read for the presence of
one key (``oauthAccount``) and nothing else; ``.credentials.json`` and the OS keychain are never
touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from codex_setup.core import paths
from codex_setup.core.errors import ConfigParseError, ConfigWriteError

PREFERRED = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}
FAMILIES = ("opus", "sonnet", "haiku")
TOKEN_KEY = "ANTHROPIC_AUTH_TOKEN"
BACKUP_PREFIX = "claude-settings"


def origin_of(base_url: str) -> str:
    """``https://host`` (no path, no ``/v1``) from any Lunovant URL."""
    parts = urlsplit((base_url or "").strip())
    return f"{parts.scheme}://{parts.netloc}"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_claude_model(name: str) -> bool:
    return name.strip().lower().startswith("claude-")


def _version_key(name: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", name))


def pick_models(available: list[str]) -> dict[str, str]:
    """The three models we configure: the preferred id when offered, else the newest id of that
    family. A family with nothing available falls back to another family's pick (so the three
    env values are always set as long as one Claude model exists). Empty dict if none."""
    claude = [m for m in available if is_claude_model(m)]
    picks: dict[str, str] = {}
    for fam in FAMILIES:
        if PREFERRED[fam] in claude:
            picks[fam] = PREFERRED[fam]
            continue
        cands = [m for m in claude if re.search(rf"(^|-){fam}(-|$)", m.lower())]
        if cands:
            picks[fam] = sorted(cands, key=lambda m: (_version_key(m), m))[-1]
    if not picks:
        return {}
    first = next(iter(picks.values()))
    for fam in FAMILIES:
        picks.setdefault(fam, first)
    return picks


def env_values(origin: str, key: str, picks: Mapping[str, str], default: str | None = None) -> dict[str, str]:
    """The ``env`` block. ``default`` is ``ANTHROPIC_MODEL`` (the opus pick unless overridden)."""
    return {
        "ANTHROPIC_BASE_URL": origin,
        TOKEN_KEY: key,
        "ANTHROPIC_MODEL": default or picks["opus"],
        "ANTHROPIC_DEFAULT_OPUS_MODEL": picks["opus"],
        "ANTHROPIC_DEFAULT_SONNET_MODEL": picks["sonnet"],
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": picks["haiku"],
    }


# -- reading ------------------------------------------------------------------
def read_json_object(path: Path) -> tuple[dict[str, Any], str | None]:
    """(data, raw text). Missing file -> ({}, None). Invalid / non-object JSON raises, so a
    hand-edited file is never overwritten blindly."""
    try:
        text = Path(path).read_bytes().decode("utf-8-sig")
    except FileNotFoundError:
        return {}, None
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigParseError(f"Cannot read {path}: {exc}", path=Path(path)) from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ConfigParseError(f"{path} is not valid JSON ({exc}); nothing was changed",
                               path=Path(path)) from exc
    if not isinstance(data, dict):
        raise ConfigParseError(f"{path} must contain a JSON object; nothing was changed",
                               path=Path(path))
    env = data.get("env")
    if env is not None and not isinstance(env, dict):
        raise ConfigParseError(f'"env" in {path} must be an object; nothing was changed',
                               path=Path(path))
    return data, text


def dumps(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def personal_login_present(env: Mapping[str, str] | None = None) -> bool:
    """True when ``.claude.json`` has a non-empty ``oauthAccount``. Only that key's presence
    is evaluated: its content (email, ids...) is never kept, logged or returned."""
    try:
        data = json.loads(paths.claude_global_state_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and bool(data.get("oauthAccount"))


# -- editing (pure) -----------------------------------------------------------
def apply_env(data: dict[str, Any], vals: Mapping[str, str], rec: dict[str, Any]) -> None:
    """Write ``vals`` into ``data['env']``; update ownership ``rec`` in place.

    ``rec['written']`` maps key -> sha256 of the value we wrote; ``rec['prev']`` keeps the
    non-token values of the user's own that we displaced (first one wins, so a re-run never
    mistakes our value for theirs); ``rec['prev_token']`` only notes that a token existed.
    """
    env = data.get("env")
    if not isinstance(env, dict):
        env = {}
    written: dict[str, str] = rec.setdefault("written", {})
    prev: dict[str, str] = rec.setdefault("prev", {})
    for k, v in vals.items():
        if k in env and isinstance(env[k], str) and env[k] != v and sha(env[k]) != written.get(k):
            if k == TOKEN_KEY:
                rec["prev_token"] = True
            else:
                prev.setdefault(k, env[k])
        env[k] = v
        written[k] = sha(v)
    data["env"] = env


def _backup_token(path: Any) -> str | None:
    """The user's own token, read back from the private backup taken before we replaced it
    (never kept in state)."""
    if not path:
        return None
    try:
        data, _ = read_json_object(Path(path))
    except ConfigParseError:
        return None
    value = (data.get("env") or {}).get(TOKEN_KEY)
    return value if isinstance(value, str) else None


def remove_env(data: dict[str, Any], rec: dict[str, Any]) -> list[str]:
    """Remove only the values we wrote and that are still unchanged; bring back displaced user
    values. Returns the keys left alone because the user changed them. Clears ownership."""
    env = data.get("env")
    skipped: list[str] = []
    written: dict[str, str] = rec.get("written") or {}
    prev: dict[str, str] = rec.get("prev") or {}
    if isinstance(env, dict):
        for k, digest in written.items():
            cur = env.get(k)
            if cur is None:
                continue
            if isinstance(cur, str) and sha(cur) == digest:
                del env[k]
                if k in prev:
                    env[k] = prev[k]
                elif k == TOKEN_KEY and rec.get("prev_token"):
                    old = _backup_token(rec.get("prev_token_backup"))
                    if old is not None:
                        env[k] = old
            else:
                skipped.append(k)
        if not env:
            data.pop("env", None)
    rec["written"] = {}
    rec["prev"] = {}
    rec.pop("prev_token", None)
    rec.pop("prev_token_backup", None)
    return skipped


def profile_text(vals: Mapping[str, str]) -> str:
    return dumps({"env": dict(vals)})


def read_profile_env(path: Path) -> dict[str, str] | None:
    """The ``env`` block of our profile file, or None if missing / not ours."""
    try:
        data, _ = read_json_object(path)
    except ConfigParseError:
        return None
    env = data.get("env")
    if not isinstance(env, dict) or not isinstance(env.get("ANTHROPIC_BASE_URL"), str) \
            or not isinstance(env.get(TOKEN_KEY), str):
        return None
    return {k: v for k, v in env.items() if isinstance(v, str)}


# -- writing ------------------------------------------------------------------
def write_private(path: Path, text: str) -> None:
    """Atomic write; the file is 0600 from the moment it exists (it holds the key)."""
    path = Path(path)
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:  # mkstemp creates the file 0600
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        if os.name == "posix":
            os.chmod(tmp_name, 0o600)
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
