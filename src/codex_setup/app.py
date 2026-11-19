"""Service layer shared by the CLI and the TUI.

Every write goes through ``_edit``: load -> original snapshot -> mutate -> save (diff, backup,
atomic write, verify, rollback). Keys never leave this layer except through ``SecretStore``,
the launcher and the opt-in persistent env helpers.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import tomlkit

from codex_setup.core import backup as backup_mod
import json

from codex_setup.core import claude_config, codex_config, model_catalog, paths
from codex_setup.core.backup import BackupInfo
from codex_setup.core.config_store import (
    diff_text,
    SaveResult,
    atomic_write_text,
    load_config,
    save_config,
)
from codex_setup.core.errors import (
    CodexSetupError,
    ConfigParseError,
    ConfigWriteError,
    SecretStoreError,
    ValidationError,
)
from codex_setup.core.state import (
    AppState,
    ConfigOwnership,
    Profile,
    config_key,
    load_state,
    save_state,
)
from codex_setup.diagnostics import knowledge
from codex_setup.diagnostics.api_test import ApiTestReport, run_api_test
from codex_setup.diagnostics import model_probe
from codex_setup.diagnostics.checks import CheckResult, DiagnosticsContext, run_checks
from codex_setup.platforms import shellrc, windows
from codex_setup.platforms.base import (
    CodexInstall,
    PlatformInfo,
    detect_codex,
    detect_platform,
)
from codex_setup.providers.catalog import (
    DEFAULT_MODEL,
    LUNOVANT,
    LUNOVANT_MODELS,
    OPENAI,
    ProviderSpec,
    custom_provider,
    normalize_base_url,
    suggest_v1,
    validate_model_name,
)
from codex_setup.security import launcher
from codex_setup.security.redact import mask_key
from codex_setup.security.secrets import SecretStore


PROFILE_NAME = "lunovant"
LEGACY_PROFILE_HEADER = "# Managed by Codex Setup " + "Manager: use with  codex -p lunovant"  # still recognised on existing files
PROFILE_HEADER = "# Managed by Lunovant Setup: use with  codex -p lunovant"
MODES = ("lunovant", "personal")


def format_key_info(info: Mapping[str, Any] | None) -> dict[str, str | None]:
    """Presentation-neutral key info: plan omitted when unknown, remaining as ``N`` (2 decimals).

    ``expires`` is None when the key has no expiry (the caller supplies the localized text).
    """
    info = info or {}
    plan = str(info.get("plan") or "").strip() or None
    rem = info.get("remaining")
    remaining: str | None = None
    if isinstance(rem, (int, float)) and not isinstance(rem, bool):
        remaining = f"{round(float(rem), 2):g}"
    elif rem not in (None, ""):
        remaining = str(rem)
    expires = str(info.get("expires_at") or "").strip() or None
    return {"plan": plan, "remaining": remaining, "expires": expires}


def make_secret_store(backend: str = "auto", env: Mapping[str, str] | None = None) -> SecretStore:
    """Build a SecretStore. ``keyring`` is strict: it errors instead of falling back to session."""
    store = SecretStore("auto" if backend == "keyring" else backend, env=env)
    if backend == "keyring" and store.backend_name != "keyring":
        raise SecretStoreError("The OS keyring is not available on this system.")
    return store


def clean_key(key: str | None) -> str | None:
    if key is None:
        return None
    value = key.strip()
    if not value:
        raise ValidationError("API key must not be empty")
    if any(c in value for c in "\r\n\x00"):
        raise ValidationError("API key must be a single line")
    return value


_INVISIBLE = re.compile(r"[\s\u200b\u200c\u200d\u2060\ufeff]+")


def normalize_key(key: str | None) -> str:
    """Drop every whitespace / zero-width character (pasted keys often carry them)."""
    return _INVISIBLE.sub("", key or "")


@dataclass
class OneClickResult:
    ok: bool
    code: str  # "ok" | key_invalid | key_expired | not_codex_key (no gpt-*/claude-* model) | no_model_works | key_empty | network
    message: str
    key_info: dict[str, Any] = field(default_factory=dict)
    models: list[dict[str, Any]] = field(default_factory=list)
    default_model: str | None = None
    config_path: Path | None = None
    backup_path: Path | None = None
    mode: str = "lunovant"
    legacy_profile: str | None = None  # removed top-level `profile = ...` (it breaks Codex)
    legacy_profile_tables: list[str] = field(default_factory=list)  # untouched [profiles.*]
    line: str = "codex"  # "codex" | "claude": which product this result describes
    # Claude line only: the models we configure ({"opus": id, ...}), the profile file and the
    # command that always uses Lunovant.
    claude_models: dict[str, str] = field(default_factory=dict)
    profile_path: Path | None = None
    # Codex line: model catalog outcome {"ok", "listed", "hidden", "code", "params"} (summary line)
    catalog: dict[str, Any] = field(default_factory=dict)
    # one entry per product set up in this run ("codex" / "claude"); the top-level fields above
    # describe the first of them (Codex when present) so single-line callers keep working
    sections: dict[str, OneClickResult] = field(default_factory=dict)


@dataclass
class StatusInfo:
    platform: PlatformInfo
    install: CodexInstall
    config_path: Path
    config_state: str  # "ok" | "invalid" | "missing"
    config_error: str | None
    model: str | None
    model_provider: str | None
    provider_ids: list[str]
    windows_sandbox: str | None
    env_key: str | None
    base_url: str | None
    masked_key: str
    secret_backend: str | None
    last_test: dict[str, Any] | None
    active_profile: str | None


@dataclass
class Diagnosis:
    checks: list[CheckResult] = field(default_factory=list)
    issues: list[knowledge.KnownIssue] = field(default_factory=list)


@dataclass
class _Active:
    provider_id: str | None
    env_key: str | None
    base_url: str | None
    model: str | None
    table: dict[str, Any] | None


class SetupService:
    def __init__(
        self,
        env: Mapping[str, str] | None = None,
        *,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._env = env
        self._injected_store = secret_store
        self._stores: dict[str, SecretStore] = {}
        self._platform: PlatformInfo | None = None
        self._install: CodexInstall | None = None
        self._legacy: tuple[str | None, list[str]] = (None, [])
        # injectable for tests: codex binary runner / PATH lookup used by the model catalog
        self._catalog_runner: model_catalog.Runner = model_catalog.default_runner
        self._which: Callable[[str], str | None] = shutil.which

    # -- environment -------------------------------------------------------
    @property
    def env(self) -> Mapping[str, str]:
        return os.environ if self._env is None else self._env

    @property
    def config_path(self) -> Path:
        return paths.config_path(self._env)

    @property
    def platform(self) -> PlatformInfo:
        if self._platform is None:
            self._platform = detect_platform()
        return self._platform

    @property
    def install(self) -> CodexInstall:
        if self._install is None:
            self._install = detect_codex(self.platform)
        return self._install

    def refresh_install(self) -> None:
        self._install = None

    def load_state(self) -> AppState:
        return load_state(self._env)

    def secret_store(self, backend: str | None = None) -> SecretStore:
        """One SecretStore per resolved backend for the service lifetime.

        ``None`` uses the backend recorded in state (or "auto"), so a session key entered
        in Quick Setup is visible to Test/Launch in the same run.
        """
        if self._injected_store is not None:
            return self._injected_store
        if backend is None:
            backend = self.load_state().secret_backend or "auto"
        if backend not in self._stores:
            store = make_secret_store(backend, self._env)
            store = self._stores.setdefault(store.backend_name, store)
            self._stores[backend] = store
        return self._stores[backend]

    def _store_call(self, fn: Callable[..., Any], *args: Any) -> Any:
        try:
            return fn(*args)
        except CodexSetupError:
            raise
        except Exception as exc:  # backend specific errors (keyring etc.)
            raise SecretStoreError(f"Secret store failed: {exc.__class__.__name__}") from exc

    # -- ownership ---------------------------------------------------------
    def _own(self, state: AppState) -> ConfigOwnership:
        return state.configs.setdefault(config_key(self.config_path), ConfigOwnership())

    def ownership(self, state: AppState | None = None) -> ConfigOwnership:
        """Read-only view of what this tool owns in the CURRENT config.toml."""
        state = state or load_state(self._env)
        return state.configs.get(config_key(self.config_path)) or ConfigOwnership()

    @staticmethod
    def _prune(state: AppState) -> None:
        for k in [k for k, v in state.configs.items() if v.is_empty()]:
            del state.configs[k]

    @staticmethod
    def _note_credential(own: ConfigOwnership, backend: str, env_key: str) -> None:
        keys = own.credentials.setdefault(backend, [])
        if env_key not in keys:
            keys.append(env_key)

    def _upsert(
        self, doc: Any, spec: ProviderSpec, own: ConfigOwnership, bearer_token: str | None = None
    ) -> None:
        """Write a provider table, recording ownership / the values we overwrite (once)."""
        before = codex_config.provider_fields(doc, spec.id)
        had_token = codex_config.get_bearer(doc, spec.id) is not None
        codex_config.upsert_provider(doc, spec, bearer_token=bearer_token)
        if bearer_token and spec.id not in own.managed_provider_ids and before is not None:
            rec = own.bearer_tokens.setdefault(spec.id, {"prev": had_token})
            rec["sha"] = self._sha(bearer_token)
        if before is None:
            if spec.id not in own.managed_provider_ids:
                own.managed_provider_ids.append(spec.id)
        elif spec.id not in own.managed_provider_ids:
            own.overwritten.setdefault(spec.id, before)
            own.written[spec.id] = {
                "name": spec.name,
                "base_url": spec.base_url,
                "wire_api": spec.wire_api,
            }
            if not bearer_token:
                own.written[spec.id]["env_key"] = str(spec.env_key)

    # -- helpers -----------------------------------------------------------
    def _record_original(self, own: ConfigOwnership, doc: Any) -> None:
        if own.original_top_level is None:
            st = codex_config.get_status(doc)
            own.original_top_level = {"model": st.model, "model_provider": st.model_provider}
            if codex_config.get_catalog(doc) is not None:  # only recorded when the user has one
                own.original_top_level[codex_config.CATALOG_KEY] = codex_config.get_catalog(doc)

    # -- ChatGPT login / modes / profile file --------------------------------
    def chatgpt_login_present(self) -> bool:
        """True when ``$CODEX_HOME/auth.json`` is a personal ChatGPT login. Only the mode is
        inspected; token values are never kept, logged or returned."""
        try:
            data = json.loads((paths.codex_home(self._env) / "auth.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        return data.get("auth_mode") == "chatgpt" or bool(data.get("tokens"))

    def codex_installed(self) -> bool:
        """True when config.toml has our provider table."""
        if not self.config_path.exists():
            return False
        try:
            return LUNOVANT.id in codex_config.get_status(load_config(self.config_path).doc).provider_ids
        except ConfigParseError:
            return False

    def current_mode(self) -> str:
        """``lunovant`` when the top-level provider is ours, else ``personal``."""
        if not self.config_path.exists():
            return "personal"
        st = codex_config.get_status(load_config(self.config_path).doc)
        return "lunovant" if st.model_provider == LUNOVANT.id else "personal"

    @property
    def profile_file(self) -> Path:
        return paths.profile_config_path(PROFILE_NAME, self._env)

    def _profile_file_ours(self) -> bool:
        try:
            return self.profile_file.read_text(encoding="utf-8").startswith((PROFILE_HEADER, LEGACY_PROFILE_HEADER))
        except (OSError, UnicodeDecodeError):
            return False

    def _write_profile_file(self, model: str) -> None:
        """``$CODEX_HOME/lunovant.config.toml`` for ``codex -p lunovant`` (no secrets inside)."""
        path = self.profile_file
        text = self._profile_text(model)
        if text == self._read_profile_or_none():
            return
        atomic_write_text(path, text)

    def _read_profile_or_none(self) -> str | None:
        if not self.profile_file.exists():
            return None
        try:
            return self.profile_file.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return "\0unreadable"

    def _profile_text(self, model: str) -> str:
        values: dict[str, str] = {"model_provider": LUNOVANT.id, "model": model}
        catalog = self._catalog_path()
        if catalog:
            values[codex_config.CATALOG_KEY] = catalog
        return f"{PROFILE_HEADER}\n{tomlkit.dumps(values)}"

    # -- model catalog --------------------------------------------------------
    @property
    def catalog_file(self) -> Path:
        # absolute: Codex runs from other working directories than this tool
        return Path(os.path.abspath(paths.codex_home(self._env))) / model_catalog.CATALOG_FILE

    def _catalog_path(self, own: ConfigOwnership | None = None) -> str | None:
        """Absolute path of our catalog when it is recorded in state and the file exists."""
        own = own or self.ownership()
        if own.model_catalog:
            live = Path(own.model_catalog)
            pending = live.with_name(f".{live.name}.candidate")  # validated, publishing now
            if live.is_file() or pending.is_file():
                return own.model_catalog
        return None

    def _apply_catalog(self, doc: Any, own: ConfigOwnership) -> None:
        """Lunovant mode: ``model_catalog_json`` points at our catalog (when we have one)."""
        path = self._catalog_path(own)
        if path:
            codex_config.set_catalog(doc, path)

    @staticmethod
    def _restore_catalog(doc: Any, own: ConfigOwnership) -> None:
        """Personal mode / uninstall: back to the user's own value, else remove ours."""
        orig = own.original_top_level or {}
        previous = orig.get(codex_config.CATALOG_KEY)
        current = codex_config.get_catalog(doc)
        if previous is not None:
            codex_config.set_catalog(doc, previous)
        elif current is not None and current == own.model_catalog:
            codex_config.set_catalog(doc, None)

    def _catalog_owned(self, own: ConfigOwnership) -> bool:
        """The live catalog file is ours and unchanged since we wrote it."""
        return bool(
            own.model_catalog == str(self.catalog_file)
            and own.model_catalog_sha
            and model_catalog.sha256_file(self.catalog_file) == own.model_catalog_sha
        )

    @staticmethod
    def _remove_catalog_file(recorded: str | None, sha: str | None) -> None:
        """Delete a catalog we wrote, only while it still has the recorded content."""
        if not recorded or not sha:
            return
        path = Path(recorded)
        if model_catalog.sha256_file(path) == sha:
            try:
                path.unlink()
            except OSError:
                pass

    def _build_catalog(
        self, sold: list[str], default: str, replace_ok: bool = True
    ) -> model_catalog.CatalogResult:
        """Build + validate a candidate against every installed Codex (never raises)."""
        home = self.catalog_file.parent
        try:
            env = dict(self.env)
            binaries = model_catalog.find_codex_binaries(
                env=env, system=self.platform.system, home=paths._home(env),
                which=self._which, runner=self._catalog_runner,
            )
            return model_catalog.create_catalog(
                home, sold, default_model=default, env=env, binaries=binaries,
                runner=self._catalog_runner, replace_ok=replace_ok,
            )
        except Exception:  # never let the catalog break setup
            return model_catalog.CatalogResult(False, note=("catalog_failed", {"version": "?"}))

    def _prepare_profile(self, model: str) -> None:
        """Back up an existing profile file before it changes. Runs BEFORE config/state are
        written; a failed backup aborts. Profile backups live outside the config backup list
        (``backup restore`` only knows config.toml)."""
        existing = self._read_profile_or_none()
        if existing is None or existing == self._profile_text(model):
            return
        path = self.profile_file
        directory = paths.app_state_dir(self._env) / "profile-backups"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            dest = directory / f"{path.name}.{stamp}.bak"
            if os.name == "posix":
                fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as out:
                    out.write(path.read_bytes())
            else:
                dest.write_bytes(path.read_bytes())
        except OSError as exc:
            raise ConfigWriteError(
                f"Cannot back up {path}: {exc}; nothing was changed", path=path
            ) from exc

    def _remove_profile_file(self) -> None:
        if self._profile_file_ours():
            try:
                self.profile_file.unlink()
            except OSError:
                pass

    @staticmethod
    def _strip_legacy_profile(doc: Any) -> tuple[str | None, list[str]]:
        """Drop a top-level ``profile = ...`` (Codex refuses to start with it); report
        ``[profiles.*]`` tables, which Codex ignores, and leave them alone."""
        removed: str | None = None
        if "profile" in doc and not isinstance(doc["profile"], dict):
            value = doc["profile"]
            removed = str(value.unwrap() if hasattr(value, "unwrap") else value)
            del doc["profile"]
        tables = doc.get("profiles")
        names = [str(k) for k in tables.keys()] if isinstance(tables, dict) else []
        return removed, names

    def _enter_mode(self, doc: Any, own: ConfigOwnership, mode: str, model: str) -> None:
        """Set the top-level provider/model/catalog for ``mode`` (our provider table is left as is)."""
        st = codex_config.get_status(doc)
        if st.model_provider != LUNOVANT.id and own.original_top_level is not None:
            # already on the user's own values (possibly edited since we recorded them): keep
            # the record fresh so a later round trip restores what the user has now
            own.original_top_level["model"] = st.model
            own.original_top_level["model_provider"] = st.model_provider
            current = codex_config.get_catalog(doc)
            if current is None:
                own.original_top_level.pop(codex_config.CATALOG_KEY, None)
            elif current != own.model_catalog:
                own.original_top_level[codex_config.CATALOG_KEY] = current
        if mode == "lunovant":
            codex_config.set_active(doc, LUNOVANT.id, model)
            self._apply_catalog(doc, own)
        elif st.model_provider != LUNOVANT.id:
            return  # personal already: leave the top-level untouched
        else:
            orig = own.original_top_level or {}
            codex_config.restore_top_level(doc, orig.get("model"), orig.get("model_provider"))
            self._restore_catalog(doc, own)

    def _edit(
        self,
        mutate: Callable[[Any, AppState, ConfigOwnership], None],
        reason: str,
        dry_run: bool,
        *,
        before_write: Callable[[], None] | None = None,
        state_first: bool = True,
    ) -> SaveResult:
        """load -> mutate -> [save state] -> [before_write] -> write config (last).

        Ownership/originals are persisted before side effects so a failure later leaves
        state consistent (recorded originals are never overwritten by later runs).
        ``state_first=False`` (uninstall) saves state only after the config was written.
        """
        state = load_state(self._env)
        loaded = load_config(self.config_path)
        own = self._own(state)
        if not dry_run:
            backup_mod.ensure_original_snapshot(self.config_path, own, self._env)
        self._record_original(own, loaded.doc)
        removed, tables = self._strip_legacy_profile(loaded.doc)
        self._legacy = (removed, tables)
        if removed is not None:
            own.legacy_profile = {"value": removed, "tables": tables}
        mutate(loaded.doc, state, own)
        note = ("legacy_profile_removed", {"value": removed}) if removed is not None else None
        if dry_run:
            res = save_config(loaded, dry_run=True, reason=reason, env=self._env)
            if note:
                res.notes.append(note)
            return res
        self._prune(state)
        if state_first:
            save_state(state, self._env)
        if before_write is not None:
            before_write()
        result = save_config(loaded, dry_run=False, reason=reason, env=self._env)
        if note:
            result.notes.append(note)
        if not state_first:
            save_state(state, self._env)
        return result

    def _active(self, ours: bool = False) -> _Active:
        """Active provider. ``ours=True``: our provider even in personal mode."""
        path = self.config_path
        if not path.exists():
            return _Active(None, None, None, None, None)
        st = codex_config.get_status(load_config(path).doc)
        if ours and st.model_provider != LUNOVANT.id and LUNOVANT.id in st.provider_ids:
            doc = load_config(path).doc
            providers = doc.get("model_providers")
            table = codex_config._plain(providers[LUNOVANT.id]) if providers is not None else None
            prof = load_state(self._env).profiles.get(LUNOVANT.id)
            env_key = (table or {}).get("env_key") or None
            if not env_key and (table or {}).get(codex_config.BEARER_FIELD):
                env_key = LUNOVANT.env_key
            return _Active(LUNOVANT.id, env_key, (table or {}).get("base_url") or None,
                           prof.model if prof else None, table)
        table = st.active_provider
        env_key = (table or {}).get("env_key") or None
        base_url = (table or {}).get("base_url") or None
        if not env_key and (table or {}).get(codex_config.BEARER_FIELD):
            env_key = LUNOVANT.env_key  # secret-store name for the key that also sits in config
        if st.model_provider == OPENAI.id and table is None:
            env_key, base_url = OPENAI.env_key, OPENAI.base_url
        return _Active(st.model_provider, env_key, base_url, st.model, table)

    def get_key(self, env_key: str) -> str | None:
        stored = None
        try:
            stored = self.secret_store().get(env_key)
        except SecretStoreError:
            stored = None
        if not stored and "session" in self._stores:
            try:
                stored = self._stores["session"].get(env_key)
            except SecretStoreError:
                stored = None
        return stored or self.env.get(env_key) or None

    # -- status ------------------------------------------------------------
    def status(self) -> StatusInfo:
        path = self.config_path
        state = load_state(self._env)
        config_state, error = "missing", None
        model = provider = sandbox = None
        provider_ids: list[str] = []
        active = _Active(None, None, None, None, None)
        if path.exists():
            try:
                loaded = load_config(path)
                st = codex_config.get_status(loaded.doc)
                model, provider = st.model, st.model_provider
                provider_ids, sandbox = st.provider_ids, st.windows_sandbox
                config_state = "ok"
                active = self._active()
            except CodexSetupError as exc:
                config_state, error = "invalid", str(exc)
        masked = mask_key(None)
        if active.env_key:
            try:
                masked = mask_key(self.secret_store().get(active.env_key))
            except SecretStoreError:
                pass
        return StatusInfo(
            platform=self.platform,
            install=self.install,
            config_path=path,
            config_state=config_state,
            config_error=error,
            model=model,
            model_provider=provider,
            provider_ids=provider_ids,
            windows_sandbox=sandbox,
            env_key=active.env_key,
            base_url=active.base_url,
            masked_key=masked,
            secret_backend=state.secret_backend,
            last_test=state.last_test,
            active_profile=state.active_profile,
        )

    # -- quick setup / model / api ----------------------------------------
    def quick_setup(
        self,
        base_url: str | None,
        model: str,
        api_key: str | None,
        secret_backend: str = "auto",
        dry_run: bool = False,
    ) -> SaveResult:
        model = validate_model_name(model)
        key = clean_key(api_key)
        spec = LUNOVANT
        if base_url:
            url = normalize_base_url(base_url)
            if url != LUNOVANT.base_url:
                spec = replace(LUNOVANT, base_url=url)
        store = self.secret_store(secret_backend)
        env_key = spec.env_key or LUNOVANT.env_key or ""

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            if not dry_run:
                self._prepare_profile(model)
            self._upsert(doc, spec, own)
            codex_config.set_active(doc, spec.id, model)
            self._apply_catalog(doc, own)
            prev = state.profiles.get(spec.id)
            custom = list(prev.models) if prev else []
            if model not in LUNOVANT_MODELS and model not in custom:
                custom.append(model)
            state.profiles[spec.id] = Profile(spec.id, spec, model, custom)
            state.active_profile = spec.id
            state.secret_backend = store.backend_name
            if key:
                self._note_credential(own, store.backend_name, env_key)

        def before_write() -> None:
            if key:
                self._store_call(store.set, env_key, key)

        result = self._edit(mutate, "quick setup", dry_run, before_write=before_write)
        if not dry_run:
            self._write_profile_file(model)
        return result

    # -- one-click setup ----------------------------------------------------
    def one_click_setup(
        self,
        key: str,
        base_url: str | None = None,
        progress: Callable[[str, dict[str, Any]], None] | None = None,
        *,
        client: Any = None,
        mode: str = "lunovant",
        claude_mode: str | None = None,
    ) -> OneClickResult:
        """Paste a key -> verify -> detect the line(s) from ``/v1/models`` (``gpt-*`` = Codex,
        ``claude-*`` = Claude Code, both = set up both) -> probe -> write config.

        ``mode`` applies to Codex, ``claude_mode`` (default: ``mode``) to Claude Code. Each line
        writes nothing when its own checks fail. The returned object describes the first line
        set up (the first failing one if any line failed); ``sections`` holds one result per line."""

        def note(step: str, **detail: Any) -> None:
            if progress is not None:
                try:
                    progress(step, detail)
                except Exception:
                    pass

        def stop(code: str, message: str, **kw: Any) -> OneClickResult:
            note("done", ok=False, code=code, message=message)
            return OneClickResult(False, code, message, **kw)

        if mode not in MODES or (claude_mode is not None and claude_mode not in MODES):
            raise ValidationError(f"Unsupported mode: {mode!r}")
        key = normalize_key(key)
        if not key:
            return stop("key_empty", "Chưa nhập key.")
        _check_ascii = key.isascii() and key.isprintable()
        if not _check_ascii:
            return stop("key_invalid", "Key chứa ký tự lạ. Hãy copy lại key.")
        url = suggest_v1(base_url) if base_url else LUNOVANT.base_url
        http = {"client": client} if client is not None else {}

        note("check_key")
        info = model_probe.check_key(url, key, **http)
        if info.get("error"):
            return stop("network", "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.",
                        key_info=info)
        if not info["valid"]:
            return stop("key_invalid", "Key không hợp lệ.", key_info=info)
        if info["expired"]:
            when = info.get("expires_at") or "?"
            return stop("key_expired", f"Key đã hết hạn (hạn: {when}).", key_info=info)
        note("check_key", **info)

        note("fetch_models")
        fetched = [m for m in model_probe.fetch_models(url, key, **http)
                   if not model_probe.is_excluded_model(m)]
        note("fetch_models", models=fetched)
        has_codex = any(m.startswith("gpt-") for m in fetched)
        has_claude = any(claude_config.is_claude_model(m) for m in fetched)
        if not (has_codex or has_claude):
            return stop(
                "not_codex_key",
                "Key này không có model Codex (gpt-*) hay Claude (claude-*) nào.",
                key_info=info,
            )
        note("fetch_models", models=fetched, lines=[
            n for n, on in (("codex", has_codex), ("claude", has_claude)) if on])

        parts: dict[str, OneClickResult] = {}
        if has_codex:
            # Only GPT models belong to Codex; other ids (gemini-*, deepseek-*, …) are not sold for it.
            gpt = [m for m in fetched if m.startswith("gpt-")]
            parts["codex"] = self._codex_setup(key, url, info, gpt, http, note, mode)
        if has_claude:
            parts["claude"] = self._claude_setup(
                key, url, info, fetched, http, note, claude_mode or mode)
        first = parts.get("codex") or parts["claude"]
        failed = next((p for p in parts.values() if not p.ok), None)
        top = replace(failed or first, ok=failed is None, sections=parts)
        note("done", ok=top.ok, code=top.code, message=top.message, default_model=top.default_model)
        return top

    def _codex_setup(
        self,
        key: str,
        url: str,
        info: dict[str, Any],
        fetched: list[str],
        http: dict[str, Any],
        note: Callable[..., None],
        mode: str,
    ) -> OneClickResult:
        """Codex line: probe every gpt model, write config.toml. Writes nothing on failure."""

        def stop(code: str, message: str, **kw: Any) -> OneClickResult:
            return OneClickResult(False, code, message, **kw)

        fetched = [m for m in fetched if not claude_config.is_claude_model(m)]
        results = model_probe.probe_models(
            url, key, fetched, **http,
            on_result=lambda r: note(f"probe:{r['model']}", **r),
        )
        passing = [r["model"] for r in results if r["ok"]]
        if not passing:
            return stop("no_model_works", "Không model nào chạy được với key này.",
                        key_info=info, models=results)
        default = DEFAULT_MODEL if DEFAULT_MODEL in passing else passing[0]

        note("catalog")
        own0 = self.ownership()
        stale = (own0.model_catalog, own0.model_catalog_sha)
        replace_ok = not self.catalog_file.exists() or self._catalog_owned(own0)
        built = self._build_catalog(list(fetched), default, replace_ok)
        catalog_info: dict[str, Any] = (
            {"ok": True, "listed": len(built.sold), "hidden": len(built.hidden)}
            if built.ok else
            {"ok": False, "code": built.note[0] if built.note else "catalog_failed",
             "params": built.note[1] if built.note else {}}
        )
        catalog_path = str(built.path) if built.ok and built.path else None

        note("write_config", model=default)
        spec = replace(LUNOVANT, base_url=url) if url != LUNOVANT.base_url else LUNOVANT
        env_key = spec.env_key or ""
        stored = False
        try:
            store = self.secret_store("auto")
            self._store_call(store.set, env_key, key)
            stored = True
        except CodexSetupError:
            store = None  # best effort: the key is also in config.toml

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            self._prepare_profile(default)
            self._upsert(doc, spec, own, bearer_token=key)
            if own.model_catalog and own.model_catalog != catalog_path:
                self._restore_catalog(doc, own)  # drop a stale key that pointed at our old file
            own.model_catalog = catalog_path
            own.model_catalog_sha = built.sha if catalog_path else None
            self._enter_mode(doc, own, mode, default)
            if self.sandbox_applicable():
                st = codex_config.get_status(doc)
                if st.windows_sandbox is None:
                    orig = own.original_top_level
                    if orig is not None and "windows_sandbox" not in orig:
                        orig["windows_sandbox"] = None
                    codex_config.set_windows_sandbox(doc, "unelevated")
            prev = state.profiles.get(spec.id)
            custom = list(prev.models) if prev else []
            state.profiles[spec.id] = Profile(spec.id, spec, default, custom, bearer=True)
            state.active_profile = spec.id
            if stored and store is not None:
                state.secret_backend = store.backend_name
                self._note_credential(own, store.backend_name, env_key)
            state.one_click = {
                "when": datetime.now().astimezone().isoformat(timespec="seconds"),
                "base_url": url,
                "models": list(fetched),
                "results": results,
                "key_info": info,
                "default_model": default,
            }

        try:
            # state is saved first, then the validated candidate goes live, then config.toml
            saved = self._edit(
                mutate, "one-click setup", False,
                before_write=lambda: model_catalog.publish(built))
        finally:
            if built.candidate is not None:
                built.candidate.unlink(missing_ok=True)
        if catalog_path is None:
            self._remove_catalog_file(*stale)  # no longer referenced by config/profile
        self._write_profile_file(default)
        path = self.config_path
        removed, tables = self._legacy
        message = f"Đã cài xong. Model mặc định: {default}."
        if mode == "personal":
            message += " Tài khoản ChatGPT vẫn là mặc định; gõ `codex -p lunovant` để dùng Lunovant."
        if removed:
            message += (f' Đã xoá dòng cũ `profile = "{removed}"` trong config.toml '
                        "(Codex bản mới không khởi động được nếu còn dòng này).")
        if tables:
            message += (" Các mục [profiles.*] cũ được giữ nguyên "
                        "(Codex bản mới bỏ qua chúng).")
        return OneClickResult(
            True, "ok", message, info, results, default, path, saved.backup,
            mode=mode, legacy_profile=removed, legacy_profile_tables=tables,
            catalog=catalog_info,
        )

    def set_mode(self, mode: str, dry_run: bool = False) -> SaveResult:
        """Switch the top-level provider/model between ``lunovant`` and the user's own.

        The provider table and ``lunovant.config.toml`` stay in both modes, so
        ``codex -p lunovant`` always works."""
        if mode not in MODES:
            raise ValidationError(f"Unsupported mode: {mode!r}")
        chosen: list[str] = []

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            if LUNOVANT.id not in codex_config.get_status(doc).provider_ids:
                raise CodexSetupError("Lunovant is not set up yet. Run the setup first.")
            prof = state.profiles.get(LUNOVANT.id)
            model = (prof.model if prof else None) or (state.one_click or {}).get(
                "default_model"
            ) or DEFAULT_MODEL
            chosen.append(model)
            if not dry_run:
                self._prepare_profile(model)
            self._enter_mode(doc, own, mode, model)

        result = self._edit(mutate, f"mode {mode}", dry_run)
        if not dry_run and chosen:
            self._write_profile_file(chosen[0])
        return result

    # -- Claude Code line ----------------------------------------------------
    CLAUDE_PROFILE_ARG = "~/.claude/lunovant-settings.json"

    @property
    def claude_settings_path(self) -> Path:
        return paths.claude_settings_path(self._env)

    @property
    def claude_profile_path(self) -> Path:
        return paths.claude_profile_path(self._env)

    def claude_login_present(self) -> bool:
        """True when ``.claude.json`` has a personal ``oauthAccount`` (presence only)."""
        return claude_config.personal_login_present(self._env)

    def claude_installed(self) -> bool:
        rec = load_state(self._env).claude
        return bool(
            rec
            and rec.get("settings_path") == str(self.claude_settings_path)
            and claude_config.read_profile_env(self.claude_profile_path) is not None
        )

    def claude_current_mode(self) -> str:
        """``lunovant`` when settings.json carries the same endpoint + token as our profile."""
        prof = claude_config.read_profile_env(self.claude_profile_path)
        if not prof:
            return "personal"
        try:
            data, _ = claude_config.read_json_object(self.claude_settings_path)
        except ConfigParseError:
            return "personal"
        env = data.get("env") or {}
        same = all(env.get(k) == prof[k] for k in ("ANTHROPIC_BASE_URL", claude_config.TOKEN_KEY))
        return "lunovant" if same else "personal"

    def claude_profile_arg(self) -> str:
        """Shell-ready path of the profile file for ``--settings``: the ``~`` form at the default
        location, else the real path (``CLAUDE_CONFIG_DIR``), quoted for the platform."""
        if not (self.env.get("CLAUDE_CONFIG_DIR") or "").strip():
            return self.CLAUDE_PROFILE_ARG
        path = str(self.claude_profile_path)
        if self.platform.system == "windows":
            return f'"{path}"' if " " in path else path
        return shlex.quote(path)

    def claude_profile_command(self) -> str:
        return f"claude --settings {self.claude_profile_arg()}"

    def claude_launch_command(self, mode: str | None = None) -> str:
        """What to type in a terminal: plain ``claude`` when Lunovant is the default, else the
        ``--settings`` form that always uses Lunovant."""
        mode = mode or self.claude_current_mode()
        return "claude" if mode == "lunovant" else self.claude_profile_command()

    @staticmethod
    def _mask_secrets(text: str) -> str:
        return re.sub(
            r'("[A-Za-z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)[A-Za-z0-9_]*"\s*:\s*")[^"]*(")',
            r"\1****\2", text, flags=re.IGNORECASE,
        )

    def _claude_edit(
        self,
        mutate: Callable[[dict[str, Any], dict[str, Any]], None],
        reason: str,
        dry_run: bool,
        *,
        extra: dict[str, Any] | None = None,
        clear: bool = False,
        state_last: bool = False,
        before_write: Callable[[], None] | None = None,
    ) -> SaveResult:
        """load settings.json -> mutate(data, ownership) -> [backup, save state] -> write.

        Never writes unparsable input; the first touch snapshots the original, and when the
        result equals that original the original bytes are written back (exact round trip).
        Diffs mask token-like values. ``state_last`` (ownership-removing operations) saves the
        state only after the file was written, so a failed write can be retried."""
        path = self.claude_settings_path
        state = load_state(self._env)
        old = state.claude if state.claude and state.claude.get("settings_path") == str(path) else None
        rec: dict[str, Any] = json.loads(json.dumps(old)) if old else {
            "settings_path": str(path), "written": {}, "prev": {}}
        data, old_text = claude_config.read_json_object(path)
        mutate(data, rec)
        if extra:
            rec.update(extra)
        new_text: str | None = claude_config.dumps(data)
        orig = rec.get("original_backup")
        if not rec.get("written") and orig and Path(orig).is_file():
            try:
                orig_data, _ = claude_config.read_json_object(Path(orig))
                if orig_data == data:
                    new_text = Path(orig).read_bytes().decode("utf-8")
            except (ConfigParseError, OSError, UnicodeDecodeError):
                pass
        if rec.get("original_exists") is False and not data:
            new_text = None  # we created the file; nothing of the user's is left in it
        if old_text is None and new_text is not None and not data and not rec.get("written"):
            new_text = None  # do not create an empty settings.json
        changed = new_text != old_text
        diff = diff_text(
            self._mask_secrets(old_text or ""), self._mask_secrets(new_text or ""), path
        ) if changed else ""
        if dry_run:
            return SaveResult(changed, diff, None, True)
        backup: Path | None = None
        if "original_exists" not in rec:
            rec["original_exists"] = old_text is not None
            if old_text is not None:
                backup = backup_mod.create_backup(
                    path, "original", self._env,
                    prefix=claude_config.BACKUP_PREFIX, suffix=".json")
                rec["original_backup"] = str(backup)
        if changed and old_text is not None and backup is None:
            backup = backup_mod.create_backup(
                path, reason, self._env, prefix=claude_config.BACKUP_PREFIX, suffix=".json")
        if rec.get("prev_token") and not rec.get("prev_token_backup") and backup is not None:
            rec["prev_token_backup"] = str(backup)  # private copy that still holds their token
        state.claude = None if clear else rec
        if not state_last:
            save_state(state, self._env)
        if before_write is not None:
            before_write()
        if changed:
            if new_text is None:
                path.unlink(missing_ok=True)
            else:
                claude_config.write_private(path, new_text)
        if state_last:
            save_state(state, self._env)
        return SaveResult(changed, diff, backup, False)

    def _write_claude_profile(self, vals: dict[str, str]) -> None:
        """``~/.claude/lunovant-settings.json``: only the env block, 0600 (it holds the key)."""
        path = self.claude_profile_path
        text = claude_config.profile_text(vals)
        try:
            existing = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            existing = None
        if existing == text:
            return
        if existing is not None:
            backup_mod.create_backup(path, "claude profile", self._env,
                                     prefix="claude-profile", suffix=".json")
        claude_config.write_private(path, text)

    def _claude_setup(
        self,
        key: str,
        url: str,
        info: dict[str, Any],
        fetched: list[str],
        http: dict[str, Any],
        note: Callable[..., None],
        mode: str,
    ) -> OneClickResult:
        """Claude Code line: probe only the three models we configure, write settings.json and
        the profile file. Writes nothing on failure."""
        available = [m for m in fetched if claude_config.is_claude_model(m)]
        picks = claude_config.pick_models(available)
        order = [picks[f] for f in claude_config.FAMILIES]
        targets = list(dict.fromkeys(order))
        note("claude_models", models=available, targets=targets)
        probed = model_probe.probe_claude_models(
            url, key, targets, **http,
            on_result=lambda r: note(f"claude_probe:{r['model']}", **r),
        )
        for r in probed:
            r["role"] = "/".join(f for f in claude_config.FAMILIES if picks[f] == r["model"])
        rows: list[dict[str, Any]] = probed + [
            {"model": m, "ok": None, "tested": False, "latency_ms": None,
             "status_code": None, "error": None}
            for m in available if m not in targets
        ]
        passing = {r["model"] for r in probed if r["ok"]}
        if not passing:
            return OneClickResult(False, "no_model_works", "Không model Claude nào chạy được "
                                  "với key này.", info, rows, line="claude")
        default = next(m for m in order if m in passing)
        final = {f: (picks[f] if picks[f] in passing else default) for f in claude_config.FAMILIES}
        origin = claude_config.origin_of(url)
        vals = claude_config.env_values(origin, key, final, default)

        note("claude_write", model=default)
        profile = self.claude_profile_path
        try:
            old_profile = profile.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            old_profile = None

        def mutate(data: dict[str, Any], rec: dict[str, Any]) -> None:
            if mode == "lunovant":
                claude_config.apply_env(data, vals, rec)
            else:
                claude_config.remove_env(data, rec)

        try:
            saved = self._claude_edit(
                mutate, "claude setup", False,
                before_write=lambda: self._write_claude_profile(vals),
                extra={"mode": mode, "profile_sha": claude_config.sha(
                    claude_config.profile_text(vals)), "one_click": {
                "when": datetime.now().astimezone().isoformat(timespec="seconds"),
                "base_url": origin, "models": available, "results": rows, "key_info": info,
                "default_model": default, "picks": final}},
            )
        except Exception:
            # settings.json could not be committed: put the previous profile back
            try:
                if old_profile is None:
                    profile.unlink(missing_ok=True)
                else:
                    claude_config.write_private(profile, old_profile)
            except OSError:
                pass
            raise
        message = f"Đã cài xong Claude Code. Model mặc định: {default}."
        if mode == "personal":
            message += (" Tài khoản Claude cá nhân vẫn là mặc định; gõ "
                        f"`{self.claude_profile_command()}` để dùng Lunovant.")
        return OneClickResult(
            True, "ok", message, info, rows, default, self.claude_settings_path, saved.backup,
            mode=mode, line="claude", claude_models=final, profile_path=self.claude_profile_path,
        )

    def claude_set_mode(self, mode: str, dry_run: bool = False) -> SaveResult:
        """``lunovant``: our env in settings.json (taken from the profile file).
        ``personal``: our unchanged env keys removed; the profile file stays, so
        ``claude --settings ~/.claude/lunovant-settings.json`` keeps working."""
        if mode not in MODES:
            raise ValidationError(f"Unsupported mode: {mode!r}")
        vals = claude_config.read_profile_env(self.claude_profile_path)
        rec = load_state(self._env).claude
        if vals is None or not rec:
            raise CodexSetupError("Lunovant for Claude Code is not set up yet. Run the setup first.")
        skipped: list[str] = []

        def mutate(data: dict[str, Any], own: dict[str, Any]) -> None:
            if mode == "lunovant":
                claude_config.apply_env(data, vals, own)
            else:
                skipped.extend(claude_config.remove_env(data, own))

        res = self._claude_edit(mutate, f"claude mode {mode}", dry_run, extra={"mode": mode},
                                state_last=(mode == "personal"))
        res.notes.extend(("un_claude_field_changed", {"field": k}) for k in skipped)
        return res

    def _claude_uninstall(self, dry_run: bool) -> SaveResult | None:
        rec = load_state(self._env).claude
        if not rec or rec.get("settings_path") != str(self.claude_settings_path):
            return None
        skipped: list[str] = []
        res = self._claude_edit(
            lambda data, own: skipped.extend(claude_config.remove_env(data, own)),
            "claude uninstall", dry_run, clear=True, state_last=True)
        profile = self.claude_profile_path
        if profile.exists():
            try:
                ours = claude_config.sha(profile.read_bytes().decode("utf-8")) == rec.get("profile_sha")
            except (OSError, UnicodeDecodeError):
                ours = False
            if not ours:
                res.notes.append(("un_claude_profile_changed", {"path": str(profile)}))
            elif not dry_run:
                profile.unlink(missing_ok=True)
        res.notes.extend(("un_claude_field_changed", {"field": k}) for k in skipped)
        return res

    def set_default_model(self, model: str, dry_run: bool = False) -> SaveResult:
        """Change only the top-level ``model``."""
        return self.change_model(model, dry_run)

    def change_model(self, model: str, dry_run: bool = False) -> SaveResult:
        model = validate_model_name(model)

        sync: list[str] = []

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            st = codex_config.get_status(doc)
            if (st.model_provider != LUNOVANT.id and LUNOVANT.id in st.provider_ids
                    and self._profile_file_ours()):
                # personal mode: the top-level model belongs to the user; only our profile moves
                prof = state.profiles.get(LUNOVANT.id)
                if prof is not None:
                    prof.model = model
                sync.append(model)
                if not dry_run:
                    self._prepare_profile(model)
                return
            codex_config.set_model(doc, model)
            prof = state.profiles.get(state.active_profile or "")
            if prof is not None:
                prof.model = model
            if st.model_provider == LUNOVANT.id and self._profile_file_ours():
                sync.append(model)
                if not dry_run:
                    self._prepare_profile(model)

        result = self._edit(mutate, "change model", dry_run)
        if sync and not dry_run:
            self._write_profile_file(sync[0])
        return result

    def set_api(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        delete_key: bool = False,
        dry_run: bool = False,
    ) -> SaveResult:
        key = clean_key(api_key)
        if key and delete_key:
            raise ValidationError("Choose either a new key or --delete-key, not both")
        active = self._active()
        if (active.table or {}).get(codex_config.BEARER_FIELD) and (key or delete_key or base_url):
            return self._set_api_bearer(active, base_url, key, delete_key, dry_run)
        if base_url is None:
            result = SaveResult(False, "", None, dry_run)
            if not (key or delete_key):
                return result
            env_key = self._require_env_key()
            if dry_run:
                return result
            store = self.secret_store()
            if key:
                state = load_state(self._env)
                self._note_credential(self._own(state), store.backend_name, env_key)
                state.secret_backend = store.backend_name
                save_state(state, self._env)  # state first, then the secret
                self._store_call(store.set, env_key, key)
            else:
                self._store_call(store.delete, env_key)
            return result

        url = normalize_base_url(base_url)
        holder: dict[str, str] = {}

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            st = codex_config.get_status(doc)
            pid, table = st.model_provider, st.active_provider
            if not pid or pid in codex_config.RESERVED_PROVIDER_IDS or not table:
                raise CodexSetupError("No custom provider is active. Run `lunovant-setup setup`.")
            env_key = table.get("env_key")
            if not env_key:
                raise CodexSetupError(f"[model_providers.{pid}] has no env_key")
            spec = ProviderSpec(
                pid, str(table.get("name", pid)), url, str(env_key),
                str(table.get("wire_api", "responses")),
            )
            self._upsert(doc, spec, own)
            holder["env_key"] = str(env_key)
            prof = state.profiles.get(pid)
            if prof is not None:
                prof.provider = replace(prof.provider, base_url=url)
            if key:
                self._note_credential(own, self.secret_store().backend_name, str(env_key))
                state.secret_backend = self.secret_store().backend_name

        def before_write() -> None:
            if key:
                self._store_call(self.secret_store().set, holder["env_key"], key)
            elif delete_key:
                self._store_call(self.secret_store().delete, holder["env_key"])

        return self._edit(mutate, "change api url", dry_run, before_write=before_write)

    def _set_api_bearer(
        self, active: _Active, base_url: str | None, key: str | None, delete_key: bool,
        dry_run: bool,
    ) -> SaveResult:
        """set_api for a provider that keeps its key in config.toml (experimental_bearer_token)."""
        url = normalize_base_url(base_url) if base_url else None
        env_key = active.env_key or LUNOVANT.env_key or ""
        pid = active.provider_id or ""

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            table = codex_config.get_status(doc).active_provider or {}
            token = key or (None if delete_key else codex_config.get_bearer(doc, pid))
            if token:
                spec = ProviderSpec(
                    pid, str(table.get("name", pid)), url or str(table.get("base_url", "")),
                    env_key, str(table.get("wire_api", "responses")),
                )
                self._upsert(doc, spec, own, bearer_token=token)
                prof = state.profiles.get(pid)
                if prof is not None and url:
                    prof.provider = replace(prof.provider, base_url=url)
            else:
                codex_config.set_bearer(doc, pid, None)
            if key:
                backend = self.secret_store().backend_name
                self._note_credential(own, backend, env_key)
                state.secret_backend = backend

        def before_write() -> None:
            if key:
                self._store_call(self.secret_store().set, env_key, key)
            elif delete_key:
                self._store_call(self.secret_store().delete, env_key)

        return self._edit(mutate, "change api (bearer)", dry_run, before_write=before_write)

    def _require_env_key(self) -> str:
        active = self._active()
        if not active.env_key:
            raise CodexSetupError("No active provider with an env_key. Run `lunovant-setup setup`.")
        return active.env_key

    # -- test --------------------------------------------------------------
    def test(self, model: str | None = None) -> ApiTestReport:
        active = self._active()
        bearer = (active.table or {}).get(codex_config.BEARER_FIELD)
        if not active.base_url or not (active.env_key or bearer):
            raise CodexSetupError("No active provider to test. Run `lunovant-setup setup`.")
        key = (self.get_key(active.env_key) if active.env_key else None) or bearer
        if not key:
            raise CodexSetupError(f"No API key found for {active.env_key}. Run `lunovant-setup api --key-stdin`.")
        used = validate_model_name(model) if model else (active.model or DEFAULT_MODEL)
        report = run_api_test(active.base_url, key, used)
        state = load_state(self._env)
        state.last_test = {
            "when": datetime.now().astimezone().isoformat(timespec="seconds"),
            "overall": report.overall.value,
            "model": used,
        }
        save_state(state, self._env)
        return report

    # -- sandbox -----------------------------------------------------------
    def sandbox_applicable(self) -> bool:
        return self.platform.system == "windows"

    def sandbox(self, mode: str | None, dry_run: bool = False) -> SaveResult | None:
        """``mode`` is elevated | unelevated | remove | None (= remove). None result: not Windows."""
        if not self.sandbox_applicable():
            return None
        if mode not in (None, "elevated", "unelevated", "remove"):
            raise ValidationError(f"Unsupported sandbox mode: {mode!r}")
        new = None if mode in (None, "remove") else mode

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            orig = own.original_top_level
            if orig is not None and "windows_sandbox" not in orig:
                orig["windows_sandbox"] = codex_config.get_status(doc).windows_sandbox
            codex_config.set_windows_sandbox(doc, new)  # type: ignore[arg-type]

        return self._edit(mutate, f"windows sandbox {mode or 'remove'}", dry_run)

    # -- backups -----------------------------------------------------------
    def backup_create(self, dry_run: bool = False) -> Path | None:
        if not self.config_path.exists():
            raise CodexSetupError("config.toml does not exist yet; nothing to back up.")
        if dry_run:
            return None
        return backup_mod.create_backup(self.config_path, "manual", self._env)

    def backup_list(self) -> list[BackupInfo]:
        return backup_mod.list_backups(self._env)

    def backup_restore(self, backup_id: str, dry_run: bool = False) -> SaveResult:
        info = backup_mod.find_backup(backup_id, self._env)
        return backup_mod.restore_backup(info, self.config_path, dry_run=dry_run, env=self._env)

    def backup_original(self, dry_run: bool = False) -> SaveResult:
        snap = self.ownership().original_snapshot
        if not snap:
            raise CodexSetupError("There is no original backup file (none was needed or taken).")
        return self.backup_restore(snap, dry_run)

    # -- diagnostics -------------------------------------------------------
    def diagnose(self, text: str | None = None) -> Diagnosis:
        if text:
            return Diagnosis([], knowledge.lookup(text))
        ctx = DiagnosticsContext(
            config_path=self.config_path,
            env=self.env,
            platform=self.platform,
            install=self.install,
            state=load_state(self._env),
            secret_store=self.secret_store(),
        )
        return Diagnosis(run_checks(ctx), [])

    # -- profiles ----------------------------------------------------------
    def list_profiles(self) -> list[Profile]:
        return list(load_state(self._env).profiles.values())

    def add_profile(
        self,
        name: str,
        base_url: str | None = None,
        env_key: str | None = None,
        model: str = DEFAULT_MODEL,
        models: list[str] | None = None,
        dry_run: bool = False,
    ) -> Profile:
        model = validate_model_name(model)
        extra = [validate_model_name(m) for m in (models or [])]
        if name == OPENAI.id:
            spec = OPENAI
        else:
            if not base_url or not env_key:
                raise ValidationError("A custom profile needs --base-url and --env-key")
            spec = custom_provider(name, name, base_url, env_key)
        state = load_state(self._env)
        profile = Profile(name, spec, model, extra)
        if dry_run:
            return profile
        state.profiles[name] = profile
        save_state(state, self._env)
        return profile

    def use_profile(self, name: str, dry_run: bool = False) -> SaveResult:
        state0 = load_state(self._env)
        profile = state0.profiles.get(name)
        if profile is None:
            raise CodexSetupError(f"Profile not found: {name}")
        spec = profile.provider

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            if not spec.builtin:
                token = None
                if profile.bearer:
                    token = codex_config.get_bearer(doc, spec.id) or self.get_key(spec.env_key or "")
                    if not token:
                        raise CodexSetupError("No API key stored for this profile. Run one-click setup again.")
                self._upsert(doc, spec, own, bearer_token=token)
            codex_config.set_active(doc, spec.id, profile.model)
            state.active_profile = name

        return self._edit(mutate, f"use profile {name}", dry_run)

    def remove_profile(self, name: str, dry_run: bool = False) -> None:
        state = load_state(self._env)
        if name not in state.profiles:
            raise CodexSetupError(f"Profile not found: {name}")
        if state.active_profile == name:
            raise CodexSetupError("Cannot remove the active profile; switch to another first.")
        if dry_run:
            return
        del state.profiles[name]
        save_state(state, self._env)

    def _active_profile(self, state: AppState) -> Profile:
        prof = state.profiles.get(state.active_profile or "")
        if prof is None:
            raise CodexSetupError("No active profile. Run Quick Setup first.")
        return prof

    def available_models(self) -> list[str]:
        state = load_state(self._env)
        prof = state.profiles.get(state.active_profile or "")
        names: list[str] = []
        if prof is None or prof.provider.id == LUNOVANT.id:
            saved = state.one_click or {}
            working = [r["model"] for r in saved.get("results", [])
                       if isinstance(r, dict) and r.get("ok") and r.get("model")]
            listed = [m for m in saved.get("models", []) if isinstance(m, str)]
            names.extend(working or listed or LUNOVANT_MODELS)
        if prof is not None:
            names.extend(prof.models)
        return [n for n in dict.fromkeys(names) if not model_probe.is_excluded_model(n)]

    def custom_models(self) -> list[str]:
        state = load_state(self._env)
        prof = state.profiles.get(state.active_profile or "")
        return list(prof.models) if prof else []

    def add_custom_model(self, name: str, dry_run: bool = False) -> None:
        name = validate_model_name(name)
        state = load_state(self._env)
        prof = self._active_profile(state)
        if dry_run:
            return
        if name not in prof.models:
            prof.models.append(name)
        save_state(state, self._env)

    def edit_custom_model(self, old: str, new: str, dry_run: bool = False) -> None:
        new = validate_model_name(new)
        state = load_state(self._env)
        prof = self._active_profile(state)
        if old not in prof.models:
            raise CodexSetupError(f"Custom model not found: {old}")
        if dry_run:
            return
        prof.models[prof.models.index(old)] = new
        save_state(state, self._env)

    def remove_custom_model(self, name: str, dry_run: bool = False) -> None:
        state = load_state(self._env)
        prof = self._active_profile(state)
        if name not in prof.models:
            raise CodexSetupError(f"Custom model not found: {name}")
        if dry_run:
            return
        prof.models.remove(name)
        save_state(state, self._env)

    # -- launch / persistent env ------------------------------------------
    def launch(self, target: str = "cli", args: list[str] | None = None) -> int:
        active = self._active()
        if not active.env_key:
            raise CodexSetupError("No active provider. Run `lunovant-setup setup`.")
        key = self.get_key(active.env_key) or (active.table or {}).get(codex_config.BEARER_FIELD)
        if not key:
            raise CodexSetupError(f"No API key found for {active.env_key}.")
        if target == "cli":
            if not self.install.cli_path:
                raise CodexSetupError("Codex CLI was not found on PATH.")
            return launcher.launch_cli(
                list(args or []), active.env_key, key, codex_path=self.install.cli_path
            )
        if target == "app":
            launcher.launch_desktop(self.install, self.platform, active.env_key, key)
            return 0
        raise ValidationError(f"Unknown launch target: {target!r}")

    def _rc_path(self) -> Path:
        home = Path(self.env.get("HOME") or Path.home())
        return shellrc.choose_rc(self.env.get("SHELL"), home)

    @staticmethod
    def _sha(text: str | None) -> str | None:
        return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()

    def env_install(self, consent: bool, dry_run: bool = False) -> str:
        """Persist the key as a user env var / shell rc block. Returns where it was written.

        Records what was there before (registry value/type, or the previous rc block) so
        ``env_remove`` restores only what this tool changed.
        """
        if not consent:
            raise CodexSetupError("Persistent environment install needs explicit consent.")
        env_key = self._require_env_key()
        key = self.get_key(env_key)
        if not key:
            raise CodexSetupError(f"No API key found for {env_key}.")
        windows_target = self.platform.system == "windows"
        where = "HKCU\\Environment" if windows_target else str(self._rc_path())
        if dry_run:
            return where
        state = load_state(self._env)
        own = self._own(state)
        old = own.env_installs.get(env_key)
        if windows_target:
            prev = windows.get_user_env_typed(env_key)
            record = {
                "kind": "windows",
                "existed": prev is not None,
                "prev_value": prev[0] if prev else None,
                "prev_type": prev[1] if prev else None,
                "written_sha": self._sha(key),
            }
        else:
            rc = self._rc_path()
            prev_block = shellrc.read_block(rc)
            record = {
                "kind": "rc",
                "rc": str(rc),
                "prev_block": prev_block,
                "written_sha": self._sha(shellrc.block_text(env_key, key)),
            }
        if old is not None and old.get("kind") == record["kind"]:
            # keep the FIRST recorded original; only refresh what we wrote
            old["written_sha"] = record["written_sha"]
            old["rc"] = record.get("rc", old.get("rc"))
            record = old
        own.env_installs[env_key] = record
        save_state(state, self._env)  # state first
        if windows_target:
            windows.set_user_env(env_key, key)
        else:
            shellrc.install_block(Path(record["rc"]), env_key, key)
        return where

    def env_remove(self, dry_run: bool = False) -> str:
        """Undo ``env_install``. Returns removed | restored | nothing | not_owned | changed."""
        env_key = self._require_env_key()
        state = load_state(self._env)
        own = self._own(state)
        rec = own.env_installs.get(env_key)
        windows_target = self.platform.system == "windows"
        if rec is None or rec.get("kind") != ("windows" if windows_target else "rc"):
            return "not_owned"
        if windows_target:
            current = windows.get_user_env_typed(env_key)
            if current is None:
                outcome = "nothing"
            elif self._sha(current[0]) != rec.get("written_sha"):
                return "changed"
            elif rec.get("existed"):
                outcome = "restored"
            else:
                outcome = "removed"
            if dry_run:
                return outcome
            if outcome == "restored":
                windows.set_user_env(env_key, str(rec["prev_value"]), rec.get("prev_type"))
            elif outcome == "removed":
                windows.remove_user_env(env_key)
        else:
            rc = Path(str(rec["rc"]))
            current_block = shellrc.read_block(rc)
            if current_block is None:
                outcome = "nothing"
            elif self._sha(current_block) != rec.get("written_sha"):
                return "changed"
            else:
                outcome = "restored" if rec.get("prev_block") else "removed"
            if dry_run:
                return outcome
            if outcome in ("restored", "removed"):
                shellrc.write_block_text(rc, rec.get("prev_block"))
        del own.env_installs[env_key]
        self._prune(state)
        save_state(state, self._env)
        return outcome

    # -- uninstall ---------------------------------------------------------
    def uninstall(self, dry_run: bool = False, delete_secret: bool = False) -> SaveResult:
        """Undo this tool's changes on both lines (Codex config.toml, Claude settings.json)."""
        res = self._uninstall_codex(dry_run, delete_secret)
        cres = self._claude_uninstall(dry_run)
        if cres is not None:
            res.changed = res.changed or cres.changed
            res.diff = res.diff + cres.diff
            res.backup = res.backup or cres.backup
            res.notes.extend(cres.notes)
        return res

    def _uninstall_codex(self, dry_run: bool = False, delete_secret: bool = False) -> SaveResult:
        state0 = load_state(self._env)
        own0 = self.ownership(state0)
        if own0.is_empty() and not self.config_path.exists():
            return SaveResult(False, "", None, dry_run)
        notes: list[tuple[str, dict[str, str]]] = []
        env_keys: list[str] = []
        catalog_recorded: list[tuple[str | None, str | None]] = []

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            st = codex_config.get_status(doc)
            for pid in list(own.managed_provider_ids):
                if pid in st.provider_ids:
                    codex_config.remove_provider(doc, pid)
            for pid, previous in own.overwritten.items():
                skipped = codex_config.restore_provider_fields(
                    doc, pid, previous, own.written.get(pid, {})
                )
                for name in skipped:
                    notes.append(("un_field_changed", {"provider": pid, "field": name}))
            self._restore_bearer(doc, own, notes)
            if own.legacy_profile and self._legacy[0] is None:
                notes.append(("legacy_profile_removed", {"value": str(own.legacy_profile["value"])}))
            own.legacy_profile = None
            orig = own.original_top_level
            if orig is not None:
                codex_config.restore_top_level(doc, orig.get("model"), orig.get("model_provider"))
                if "windows_sandbox" in orig:
                    value = orig["windows_sandbox"]
                    if value in (None, "elevated", "unelevated"):
                        codex_config.set_windows_sandbox(doc, value)
                    else:
                        windows_tbl = doc.get("windows")
                        if windows_tbl is None:
                            windows_tbl = tomlkit.table()
                            doc.add("windows", windows_tbl)
                        windows_tbl["sandbox"] = value
            self._restore_catalog(doc, own)
            catalog_recorded.append((own.model_catalog, own.model_catalog_sha))
            own.model_catalog = None
            own.model_catalog_sha = None
            own.managed_provider_ids = []
            own.original_top_level = None
            own.original_snapshot = None
            own.overwritten = {}
            own.written = {}
            own.bearer_tokens = {}
            state.active_profile = None
            for ks in own.credentials.values():
                env_keys.extend(ks)

        result = self._edit(mutate, "uninstall", dry_run, state_first=False)
        if not dry_run:
            self._remove_profile_file()
            for recorded, sha in catalog_recorded:
                self._remove_catalog_file(recorded, sha)
        result.notes = notes + result.notes
        keys = list(dict.fromkeys(env_keys))
        if delete_secret and keys:
            if dry_run:
                result.notes.append(("un_would_delete", {"keys": ", ".join(keys)}))
            else:
                result.notes.extend(self._delete_credentials(keys))
        return result

    def _restore_bearer(
        self, doc: Any, own: ConfigOwnership, notes: list[tuple[str, dict[str, str]]]
    ) -> None:
        """Undo experimental_bearer_token changes: drop ours, bring back a previous one."""
        for pid, rec in own.bearer_tokens.items():
            current = codex_config.get_bearer(doc, pid)
            if current is None:
                continue
            if self._sha(current) != rec.get("sha"):
                notes.append(("un_field_changed", {"provider": pid, "field": codex_config.BEARER_FIELD}))
                continue
            previous = self._snapshot_bearer(own, pid) if rec.get("prev") else None
            if rec.get("prev") and previous is None:
                notes.append(("un_field_changed", {"provider": pid, "field": codex_config.BEARER_FIELD}))
                continue
            codex_config.set_bearer(doc, pid, previous)

    @staticmethod
    def _snapshot_bearer(own: ConfigOwnership, pid: str) -> str | None:
        import tomllib

        if not own.original_snapshot:
            return None
        try:
            data = tomllib.loads(Path(own.original_snapshot).read_text(encoding="utf-8"))
            value = data["model_providers"][pid][codex_config.BEARER_FIELD]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return value if isinstance(value, str) else None

    def _delete_credentials(self, keys: list[str]) -> list[tuple[str, dict[str, str]]]:
        state = load_state(self._env)
        own = self._own(state)
        by_backend = {b: list(ks) for b, ks in own.credentials.items()}
        deleted: list[str] = []
        notes: list[tuple[str, dict[str, str]]] = []
        for backend, ks in by_backend.items():
            try:
                store = self.secret_store(backend)
            except CodexSetupError as exc:
                notes.append(("un_key_failed", {"keys": ", ".join(ks), "error": str(exc)}))
                continue
            for k in ks:
                try:
                    self._store_call(store.delete, k)
                    deleted.append(k)
                    if k in own.credentials.get(backend, []):
                        own.credentials[backend].remove(k)
                except CodexSetupError as exc:
                    notes.append(("un_key_failed", {"keys": k, "error": str(exc)}))
            if backend in own.credentials and not own.credentials[backend]:
                del own.credentials[backend]
        self._prune(state)
        save_state(state, self._env)
        if deleted:
            notes.append(("un_keys_deleted", {"keys": ", ".join(dict.fromkeys(deleted))}))
        return notes


__all__ = [
    "Diagnosis",
    "SetupService",
    "StatusInfo",
    "clean_key",
    "make_secret_store",
    "ConfigParseError",
    "MODES",
    "OneClickResult",
    "PROFILE_HEADER",
    "format_key_info",
]
