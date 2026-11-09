"""Service layer shared by the CLI and the TUI.

Every write goes through ``_edit``: load -> original snapshot -> mutate -> save (diff, backup,
atomic write, verify, rollback). Keys never leave this layer except through ``SecretStore``,
the launcher and the opt-in persistent env helpers.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import tomlkit

from codex_setup.core import backup as backup_mod
from codex_setup.core import codex_config, paths
from codex_setup.core.backup import BackupInfo
from codex_setup.core.config_store import SaveResult, load_config, save_config
from codex_setup.core.errors import (
    CodexSetupError,
    ConfigParseError,
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
    validate_model_name,
)
from codex_setup.security import launcher
from codex_setup.security.redact import mask_key
from codex_setup.security.secrets import SecretStore


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

    def _upsert(self, doc: Any, spec: ProviderSpec, own: ConfigOwnership) -> None:
        """Write a provider table, recording ownership / the values we overwrite (once)."""
        before = codex_config.provider_fields(doc, spec.id)
        codex_config.upsert_provider(doc, spec)
        if before is None:
            if spec.id not in own.managed_provider_ids:
                own.managed_provider_ids.append(spec.id)
        elif spec.id not in own.managed_provider_ids:
            own.overwritten.setdefault(spec.id, before)
            own.written[spec.id] = {
                "name": spec.name,
                "base_url": spec.base_url,
                "env_key": str(spec.env_key),
                "wire_api": spec.wire_api,
            }

    # -- helpers -----------------------------------------------------------
    def _record_original(self, own: ConfigOwnership, doc: Any) -> None:
        if own.original_top_level is None:
            st = codex_config.get_status(doc)
            own.original_top_level = {"model": st.model, "model_provider": st.model_provider}

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
        mutate(loaded.doc, state, own)
        if dry_run:
            return save_config(loaded, dry_run=True, reason=reason, env=self._env)
        self._prune(state)
        if state_first:
            save_state(state, self._env)
        if before_write is not None:
            before_write()
        result = save_config(loaded, dry_run=False, reason=reason, env=self._env)
        if not state_first:
            save_state(state, self._env)
        return result

    def _active(self) -> _Active:
        path = self.config_path
        if not path.exists():
            return _Active(None, None, None, None, None)
        st = codex_config.get_status(load_config(path).doc)
        table = st.active_provider
        env_key = (table or {}).get("env_key") or None
        base_url = (table or {}).get("base_url") or None
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
            self._upsert(doc, spec, own)
            codex_config.set_active(doc, spec.id, model)
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

        return self._edit(mutate, "quick setup", dry_run, before_write=before_write)

    def change_model(self, model: str, dry_run: bool = False) -> SaveResult:
        model = validate_model_name(model)

        def mutate(doc: Any, state: AppState, own: ConfigOwnership) -> None:
            codex_config.set_model(doc, model)
            prof = state.profiles.get(state.active_profile or "")
            if prof is not None:
                prof.model = model

        return self._edit(mutate, "change model", dry_run)

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
                raise CodexSetupError("No custom provider is active. Run `codex-setup setup`.")
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

    def _require_env_key(self) -> str:
        active = self._active()
        if not active.env_key:
            raise CodexSetupError("No active provider with an env_key. Run `codex-setup setup`.")
        return active.env_key

    # -- test --------------------------------------------------------------
    def test(self, model: str | None = None) -> ApiTestReport:
        active = self._active()
        if not active.base_url or not active.env_key:
            raise CodexSetupError("No active provider to test. Run `codex-setup setup`.")
        key = self.get_key(active.env_key)
        if not key:
            raise CodexSetupError(f"No API key found for {active.env_key}. Run `codex-setup api --key-stdin`.")
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
                self._upsert(doc, spec, own)
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
            names.extend(LUNOVANT_MODELS)
        if prof is not None:
            names.extend(prof.models)
        return list(dict.fromkeys(names))

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
            raise CodexSetupError("No active provider. Run `codex-setup setup`.")
        key = self.get_key(active.env_key)
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
        state0 = load_state(self._env)
        own0 = self.ownership(state0)
        if own0.is_empty() and not self.config_path.exists():
            return SaveResult(False, "", None, dry_run)
        notes: list[tuple[str, dict[str, str]]] = []
        env_keys: list[str] = []

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
            own.managed_provider_ids = []
            own.original_top_level = None
            own.original_snapshot = None
            own.overwritten = {}
            own.written = {}
            state.active_profile = None
            for ks in own.credentials.values():
                env_keys.extend(ks)

        result = self._edit(mutate, "uninstall", dry_run, state_first=False)
        result.notes = notes
        keys = list(dict.fromkeys(env_keys))
        if delete_secret and keys:
            if dry_run:
                result.notes.append(("un_would_delete", {"keys": ", ".join(keys)}))
            else:
                result.notes.extend(self._delete_credentials(keys))
        return result

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
]
