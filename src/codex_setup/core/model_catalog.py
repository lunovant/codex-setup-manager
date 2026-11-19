"""Codex model catalog (``model_catalog_json``) for the models Lunovant sells.

Codex builds its model picker from its own catalog (bundled in each binary), not from the
provider's ``/v1/models``. This module builds a catalog from the newest installed Codex's
bundled one: sold models are listed (cloned from a sibling when the bundle lacks them), the
rest are hidden. The result is only used when EVERY installed Codex accepts it.

Pure logic + an injectable binary runner; nothing here touches config.toml or state.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATALOG_FILE = "lunovant-models.json"
FAMILIES = ("sol", "astra", "terra", "luna")
VERSION_TIMEOUT = 10.0
CATALOG_TIMEOUT = 30.0
EDITOR_DIRS = (".vscode", ".vscode-insiders", ".cursor", ".windsurf")
MAC_APP_NAMES = ("ChatGPT.app", "Codex.app")
MAC_APP_BINARIES = (
    "Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
    "Contents/Resources/codex",
)

# runner(argv, env, timeout) -> (returncode, stdout, stderr); raises OSError/TimeoutExpired
Runner = Callable[[Sequence[str], Mapping[str, str], float], tuple[int, str, str]]


class CatalogError(Exception):
    """The catalog cannot be built (reason is for logs/tests, not shown verbatim)."""


@dataclass(frozen=True)
class CodexBinary:
    path: str
    version: str

    @property
    def key(self) -> tuple[Any, ...]:
        return version_key(self.version)


@dataclass
class CatalogResult:
    ok: bool
    path: Path | None = None
    sold: list[str] = field(default_factory=list)
    cloned: list[str] = field(default_factory=list)
    hidden: list[str] = field(default_factory=list)
    note: tuple[str, dict[str, str]] | None = None  # (note code, params) when not ok
    candidate: Path | None = None  # validated file waiting to be published to ``path``
    sha: str | None = None  # sha256 of the candidate content
    binaries: list[CodexBinary] = field(default_factory=list)


def default_runner(argv: Sequence[str], env: Mapping[str, str], timeout: float) -> tuple[int, str, str]:
    proc = subprocess.run(
        list(argv), capture_output=True, text=True, timeout=timeout, check=False,
        env=dict(env), encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


# -- versions -----------------------------------------------------------------
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.\-]+))?")


def parse_version(output: str) -> str | None:
    """``codex-cli 0.169.0-alpha.11.1`` -> ``0.169.0-alpha.11.1``."""
    m = _VERSION_RE.search(output or "")
    return m.group(0) if m else None


def version_key(version: str) -> tuple[Any, ...]:
    """Sortable key (semver-like: a release outranks its pre-releases)."""
    m = _VERSION_RE.search(version or "")
    if not m:
        return ((0, 0, 0), 0, ())
    nums = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    pre = m.group(4)
    if not pre:
        return (nums, 1, ())
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return (nums, 0, parts)


# -- finding binaries -----------------------------------------------------------
def _exe(system: str) -> str:
    return "codex.exe" if system == "windows" else "codex"


def _ext_dir_version(name: str) -> tuple[Any, ...]:
    return version_key(name[len("openai.chatgpt-"):])


def extension_binaries(home: Path, system: str) -> list[Path]:
    out: list[Path] = []
    for editor in EDITOR_DIRS:
        root = home / editor / "extensions"
        try:
            dirs = [d for d in root.glob("openai.chatgpt-*") if d.is_dir()]
        except OSError:
            continue
        if not dirs:
            continue
        newest = max(_ext_dir_version(d.name) for d in dirs)
        for d in sorted(dirs):
            if _ext_dir_version(d.name) != newest:
                continue
            try:
                out.extend(sorted(d.glob(f"bin/*/{_exe(system)}")))
            except OSError:
                continue
    return out


def mac_app_binaries(home: Path, roots: Sequence[Path] | None = None) -> list[Path]:
    roots = roots if roots is not None else [Path("/Applications"), home / "Applications"]
    return [
        Path(root) / app / rel
        for root in roots
        for app in MAC_APP_NAMES
        for rel in MAC_APP_BINARIES
    ]


def find_codex_binaries(
    *,
    env: Mapping[str, str],
    system: str,
    home: Path,
    which: Callable[[str], str | None],
    runner: Runner = default_runner,
    app_roots: Sequence[Path] | None = None,
) -> list[CodexBinary]:
    """Every runnable Codex binary: PATH, macOS desktop app, IDE extensions."""
    candidates: list[str] = []
    on_path = which("codex")
    if on_path:
        candidates.append(on_path)
    if system == "macos":
        candidates.extend(str(p) for p in mac_app_binaries(home, app_roots) if p.is_file())
    candidates.extend(str(p) for p in extension_binaries(home, system) if p.is_file())
    found: list[CodexBinary] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            real = os.path.realpath(path)
        except OSError:
            real = path
        if real in seen:
            continue
        seen.add(real)
        try:
            rc, out, err = runner([path, "--version"], env, VERSION_TIMEOUT)
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        version = parse_version(out + " " + err) if rc == 0 else None
        if version:
            found.append(CodexBinary(path, version))
    return found


# -- building the catalog -----------------------------------------------------
_SLUG_RE = re.compile(r"^gpt-(\d+(?:\.\d+)*)(?:-(.+))?$")


def _parse_slug(slug: str) -> tuple[tuple[int, ...], str | None, str] | None:
    """``gpt-6.2-sol`` -> ((6, 2), "sol", "6.2")."""
    m = _SLUG_RE.match(slug)
    if not m:
        return None
    ver = m.group(1)
    return tuple(int(p) for p in ver.split(".")), m.group(2), ver


def _family(slug: str) -> str | None:
    parsed = _parse_slug(slug)
    return parsed[1] if parsed and parsed[1] in FAMILIES else None


def _replace_strings(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_replace_strings(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: _replace_strings(v, old, new) for k, v in value.items()}
    return value


def _display_name(template: Mapping[str, Any], old_slug: str, slug: str) -> str:
    new = _parse_slug(slug)
    old = _parse_slug(old_slug)
    display = str(template.get("display_name") or "")
    if new and old and display and new[1] == old[1]:  # same family: keep the naming style
        swapped = re.sub(
            r"(?<![\d.])" + re.escape(old[2]) + r"(?![\d.])", new[2], display, count=1)
        if swapped != display:
            return swapped
    if new:
        suffix = f"-{new[1].capitalize()}" if new[1] else ""
        return f"GPT-{new[2]}{suffix}"
    return slug


def _pick_template(
    slug: str, entries: Sequence[dict[str, Any]], default_model: str | None
) -> dict[str, Any]:
    family = _family(slug)
    if family:
        same = [e for e in entries if _family(str(e.get("slug"))) == family]
        if same:
            return max(same, key=lambda e: _parse_slug(str(e["slug"]))[0])  # type: ignore[index]
    if default_model:
        for e in entries:
            if e.get("slug") == default_model:
                return e
    for e in entries:
        if e.get("visibility") == "list":
            return e
    return entries[0]


def clone_entry(template: Mapping[str, Any], slug: str) -> dict[str, Any]:
    old_slug = str(template["slug"])
    old_display = str(template.get("display_name") or "")
    display = _display_name(template, old_slug, slug)
    clone = _replace_strings(copy.deepcopy(dict(template)), old_slug, slug)
    if old_display and old_display != display:
        clone = _replace_strings(clone, old_display, display)
    clone["slug"] = slug
    clone["display_name"] = display
    clone["visibility"] = "list"
    return clone


def build_catalog(
    base: Mapping[str, Any], sold: Sequence[str], default_model: str | None = None
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Return (catalog, cloned slugs, hidden slugs). ``base`` is ``{"models": [...]}``."""
    raw = base.get("models")
    if not isinstance(raw, list) or not raw or not all(isinstance(e, dict) and e.get("slug") for e in raw):
        raise CatalogError("base catalog has no models")
    entries: list[dict[str, Any]] = copy.deepcopy(raw)
    by_slug = {str(e["slug"]): e for e in entries}
    sold_set = list(dict.fromkeys(sold))
    cloned: list[str] = []
    hidden: list[str] = []
    originals = list(entries)
    missing = [s for s in sold_set if s not in by_slug]
    # newest first so same-version newcomers keep the template's relative order
    missing.sort(key=lambda s: (
        tuple(-n for n in (_parse_slug(s) or ((0,),))[0]),
        float(_pick_template(s, originals, default_model).get("priority", 0)),
        s,
    ))
    keys: dict[str, float] = {}
    for idx, slug in enumerate(missing):
        template = _pick_template(slug, originals, default_model)
        entry = clone_entry(template, slug)
        parsed = _parse_slug(slug)
        lower = [
            e for e in originals
            if e.get("visibility") == "list"
            and (_parse_slug(str(e["slug"])) or ((0,),))[0] < (parsed[0] if parsed else (0,))
        ]
        if lower:
            keys[slug] = min(float(e.get("priority", 0)) for e in lower) - 1 + idx * 0.001
        else:
            keys[slug] = max((float(e.get("priority", 0)) for e in originals), default=0) + 1 + idx * 0.001
        entries.append(entry)
        by_slug[slug] = entry
        cloned.append(slug)
    for e in entries:
        slug = str(e["slug"])
        if slug in sold_set:
            e["visibility"] = "list"
        elif e.get("visibility") == "list":
            e["visibility"] = "hide"
            hidden.append(slug)
    if cloned:
        # renumber the listed entries (ints, ascending = first in the picker), keep hidden ones
        listed = [e for e in entries if e.get("visibility") == "list"]
        listed.sort(key=lambda e: keys.get(str(e["slug"]), float(e.get("priority", 0))))
        for n, e in enumerate(listed, start=1):
            e["priority"] = n
    out = {k: v for k, v in base.items() if k != "models"}
    out["models"] = entries
    return out, cloned, hidden


def listed_slugs(catalog: Mapping[str, Any]) -> list[str]:
    return [str(e["slug"]) for e in catalog.get("models", []) if e.get("visibility") == "list"]


# -- running Codex ----------------------------------------------------------------
def _env_for(env: Mapping[str, str], codex_home: Path) -> dict[str, str]:
    out = dict(env)
    out["CODEX_HOME"] = str(codex_home)
    return out


def dump_bundled(binary: CodexBinary, env: Mapping[str, str], runner: Runner) -> dict[str, Any]:
    try:
        rc, out, _err = runner([binary.path, "debug", "models", "--bundled"], env, CATALOG_TIMEOUT)
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise CatalogError(f"cannot read bundled catalog: {exc.__class__.__name__}") from exc
    if rc != 0 or not isinstance(data, dict):
        raise CatalogError("bundled catalog dump failed")
    return data


def validate_catalog(
    binary: CodexBinary, path: Path, sold: Sequence[str], env: Mapping[str, str], runner: Runner
) -> bool:
    """``<bin> debug models -c model_catalog_json="<path>"`` must exit 0 and list every sold model."""
    override = f"model_catalog_json={json.dumps(str(path))}"  # JSON string == valid TOML basic string
    try:
        rc, out, _err = runner(
            [binary.path, "debug", "models", "-c", override], env, CATALOG_TIMEOUT)
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    if rc != 0 or not isinstance(data, dict):
        return False
    listed = {
        str(m.get("slug")) for m in data.get("models", [])
        if isinstance(m, dict) and m.get("visibility") == "list"
    }
    return all(s in listed for s in sold)


def write_private(path: Path, text: str) -> None:
    """Atomic write, 0600 on POSIX (the temp file is created private before the replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        if os.name == "posix":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        tmp = ""
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def create_catalog(
    codex_home: Path,
    sold: Sequence[str],
    *,
    default_model: str | None,
    env: Mapping[str, str],
    binaries: Sequence[CodexBinary],
    runner: Runner = default_runner,
    replace_ok: bool = True,
) -> CatalogResult:
    """Build a candidate catalog and validate it on every binary; publish it separately.

    Nothing at ``$CODEX_HOME/lunovant-models.json`` is touched here: the candidate lives in a
    private side file until :func:`publish` (so Codex never reads an unvalidated catalog).
    ``replace_ok=False`` (the target exists and is not ours) skips with a note. On failure
    ``note`` says why (the catalog must never make an installed Codex fail to start)."""
    codex_home = Path(os.path.abspath(codex_home))  # Codex runs from other directories
    path = codex_home / CATALOG_FILE
    # unique per build: concurrent builds never share (or delete) each other's candidate
    candidate = codex_home / f".{CATALOG_FILE}.{uuid.uuid4().hex}.candidate"
    sold = [s for s in dict.fromkeys(sold) if s]
    if not binaries:
        return CatalogResult(False, note=("catalog_no_codex", {}))
    if not replace_ok:
        return CatalogResult(False, note=("catalog_foreign", {}))
    newest = max(binaries, key=lambda b: b.key)
    run_env = _env_for(env, codex_home)
    try:
        if not sold:
            raise CatalogError("nothing is sold")
        base = dump_bundled(newest, run_env, runner)
        catalog, cloned, hidden = build_catalog(base, sold, default_model)
        text = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
        write_private(candidate, text)
    except (CatalogError, OSError):
        _remove(candidate)
        return CatalogResult(False, note=("catalog_failed", {"version": newest.version}),
                             binaries=list(binaries))
    for binary in binaries:
        if not validate_catalog(binary, candidate, sold, run_env, runner):
            _remove(candidate)
            return CatalogResult(False, note=("catalog_failed", {"version": binary.version}),
                                 binaries=list(binaries))
    return CatalogResult(True, path, sold, cloned, hidden, binaries=list(binaries),
                         candidate=candidate, sha=sha256_text(text))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def publish(result: CatalogResult) -> None:
    """Atomically move the validated candidate over the live catalog file."""
    if result.ok and result.candidate and result.path:
        os.replace(result.candidate, result.path)


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def current_system() -> str:
    raw = sys.platform.lower()
    if raw.startswith("win"):
        return "windows"
    return "macos" if raw == "darwin" else "linux"


def catalog_listed_count(path: Path) -> int:
    try:
        return len(listed_slugs(json.loads(path.read_text(encoding="utf-8"))))
    except (OSError, ValueError):
        return 0


__all__: Iterable[str] = [
    "CATALOG_FILE", "CatalogError", "CatalogResult", "CodexBinary", "build_catalog",
    "clone_entry", "create_catalog", "publish", "sha256_file", "find_codex_binaries", "parse_version", "version_key",
]
