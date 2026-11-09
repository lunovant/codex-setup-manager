"""Local diagnostics: config, provider, env var, secret, Codex install, sandbox log."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from codex_setup.core import codex_config
from codex_setup.core.config_store import load_config
from codex_setup.core.errors import CodexSetupError, ConfigParseError
from codex_setup.core.paths import codex_home
from codex_setup.core.state import AppState
from codex_setup.diagnostics.api_test import Outcome
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.redact import redact
from codex_setup.security.secrets import SecretStore

_ERROR_RE = re.compile(r"error|fail|denied|refused|cannot|can't|unable|exception", re.IGNORECASE)


@dataclass
class CheckResult:
    id: str
    outcome: Outcome
    title: str
    detail: str  # English, for logs/tests
    fix: str
    # stable i18n key (``dgc_*``): title = t(code), detail = t(code + "_d"), fix = t(code + "_f")
    # where those keys exist; the English fields above are the fallback.
    code: str = ""
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class DiagnosticsContext:
    config_path: Path
    env: Mapping[str, str]
    platform: PlatformInfo
    install: CodexInstall
    state: AppState
    secret_store: SecretStore


def _r(id_, outcome, title, detail="", fix="", code="", **params):
    return CheckResult(id_, outcome, title, detail, fix, code or f"dgc_{id_}",
                       {k: str(v) for k, v in params.items()})


_SENSITIVE_ENV = re.compile(r"API_?KEY|TOKEN", re.IGNORECASE)


def collect_secrets(ctx: "DiagnosticsContext", env_key: str | None, stored: str | None) -> list[str]:
    """Stored secret + the active provider's env value + any *API_KEY*/*TOKEN* env (len>=8)."""
    found: list[str] = []
    if stored:
        found.append(stored)
    if env_key and ctx.env.get(env_key):
        found.append(str(ctx.env.get(env_key)))
    for name, value in ctx.env.items():
        if _SENSITIVE_ENV.search(name) and value and len(value) >= 8:
            found.append(str(value))
    return found


def run_checks(ctx: DiagnosticsContext) -> list[CheckResult]:
    results: list[CheckResult] = []
    secrets: list[str] = []
    status = None

    # config
    if not ctx.config_path.exists():
        results.append(_r("config", Outcome.WARN, "config.toml not found", str(ctx.config_path),
                          "Run `codex-setup setup` to create it.", "dgc_config_missing",
                          path=ctx.config_path))
    else:
        try:
            loaded = load_config(ctx.config_path)
            status = codex_config.get_status(loaded.doc)
            results.append(_r("config", Outcome.OK, "config.toml parses", str(ctx.config_path),
                              code="dgc_config_ok", path=ctx.config_path))
        except ConfigParseError as exc:
            where = f" (line {exc.line}, col {exc.col})" if exc.line else ""
            results.append(_r("config", Outcome.FAIL, "config.toml is invalid", f"{exc}{where}",
                              "Fix the file or restore a backup with `codex-setup backup restore`.",
                              "dgc_config_invalid", error=f"{exc}{where}"))
        except CodexSetupError as exc:
            results.append(_r("config", Outcome.FAIL, "config.toml cannot be read", str(exc), "",
                              "dgc_config_unreadable", error=str(exc)))

    env_key: str | None = None
    if status is not None:
        provider = status.model_provider
        if not provider:
            results.append(_r("provider", Outcome.WARN, "model_provider not set",
                              "Codex uses its default provider (openai).",
                              "Run `codex-setup setup` to select a provider.", "dgc_provider_unset"))
        elif provider in codex_config.RESERVED_PROVIDER_IDS:
            results.append(_r("provider", Outcome.OK, f"Built-in provider: {provider}",
                              code="dgc_provider_builtin", provider=provider))
        elif provider not in status.provider_ids:
            results.append(_r("provider", Outcome.FAIL, "Provider mismatch",
                              f"model_provider = \"{provider}\" but no [model_providers.{provider}] table is defined.",
                              "Run `codex-setup setup` to define it, or fix model_provider.",
                              "dgc_provider_mismatch", provider=provider))
        else:
            results.append(_r("provider", Outcome.OK, f"Provider defined: {provider}",
                              code="dgc_provider_ok", provider=provider))
            table = status.active_provider or {}
            env_key = table.get("env_key") or None
            if not env_key:
                results.append(_r("env_key", Outcome.WARN, "Provider has no env_key",
                                  f"[model_providers.{provider}] does not name an API key variable.",
                                  "Run `codex-setup setup` to set env_key.", "dgc_env_key_missing",
                                  provider=provider))

    if env_key:
        stored = None
        try:
            stored = ctx.secret_store.get(env_key)
        except CodexSetupError:
            stored = None
        secrets.extend(collect_secrets(ctx, env_key, stored))
        present = bool(ctx.env.get(env_key))
        if present:
            results.append(_r("env_var", Outcome.OK, f"{env_key} is set in the environment",
                              code="dgc_env_var_ok", env_key=env_key))
        elif stored:
            results.append(_r("env_var", Outcome.WARN, f"{env_key} is not set in this environment",
                              "The key is stored but this process does not export it.",
                              "Start Codex with `codex-setup launch`, or opt in to `codex-setup env install`.",
                              "dgc_env_var_unexported", env_key=env_key))
        else:
            results.append(_r("env_var", Outcome.FAIL, f"{env_key} is not set",
                              "No environment variable and no stored key.",
                              "Run `codex-setup api --key-stdin` to store the key.",
                              "dgc_env_var_unset", env_key=env_key))
        if stored:
            results.append(_r("secret", Outcome.OK, "API key stored", f"backend: {ctx.secret_store.backend_name}",
                              code="dgc_secret_ok", backend=ctx.secret_store.backend_name))
        else:
            results.append(_r("secret", Outcome.WARN, "No API key stored", f"backend: {ctx.secret_store.backend_name}",
                              "Run `codex-setup api --key-stdin`.", "dgc_secret_missing",
                              backend=ctx.secret_store.backend_name))

    # codex install
    inst = ctx.install
    if inst.cli_path:
        results.append(_r("codex_cli", Outcome.OK, "Codex CLI found",
                          f"{inst.cli_path} ({inst.cli_version or 'version unknown'})",
                          code="dgc_codex_cli_ok", path=inst.cli_path,
                          version=inst.cli_version or "?"))
    else:
        results.append(_r("codex_cli", Outcome.WARN, "Codex CLI not found", "`codex` is not on PATH.",
                          "Install the Codex CLI and reopen the terminal.", "dgc_codex_cli_missing"))
    results.append(_r("desktop", Outcome.OK if inst.desktop_installed else Outcome.SKIP,
                      "Codex Desktop", inst.desktop_note,
                      code="dgc_desktop_ok" if inst.desktop_installed else "dgc_desktop_none"))

    # windows sandbox
    if ctx.platform.system == "windows":
        mode = status.windows_sandbox if status else None
        results.append(_r("sandbox_mode", Outcome.OK if mode else Outcome.WARN,
                          f"Windows sandbox: {mode or 'not set'}", "",
                          "" if mode else "Try `codex-setup sandbox unelevated` first.",
                          "dgc_sandbox_mode_set" if mode else "dgc_sandbox_mode_unset",
                          mode=mode or ""))
        secrets.extend(collect_secrets(ctx, env_key, None))
        log = codex_home(ctx.env, system="windows") / ".sandbox" / "sandbox.log"
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        except OSError:
            lines = []
        bad = [redact(line, secrets)[:300] for line in lines if _ERROR_RE.search(line)]
        if bad:
            results.append(_r("sandbox_log", Outcome.WARN, "Errors in sandbox.log", "\n".join(bad[-10:]),
                              "Try `codex-setup sandbox unelevated`; the tool never disables the sandbox.",
                              "dgc_sandbox_log_errors"))
        else:
            results.append(_r("sandbox_log", Outcome.OK if lines else Outcome.SKIP, "sandbox.log",
                              "No errors in the last 200 lines." if lines else "No sandbox log found.",
                              code="dgc_sandbox_log_clean" if lines else "dgc_sandbox_log_none"))

    # last test
    lt = ctx.state.last_test
    if lt:
        overall = str(lt.get("overall", "")).lower()
        oc = {"ok": Outcome.OK, "warn": Outcome.WARN, "fail": Outcome.FAIL}.get(overall, Outcome.WARN)
        results.append(_r("last_test", oc, f"Last API test: {overall or 'unknown'}",
                          f"{lt.get('when', '')} model={lt.get('model', '')}",
                          "" if oc == Outcome.OK else "Run `codex-setup test`.",
                          "dgc_last_test", overall=overall or "?"))
    else:
        results.append(_r("last_test", Outcome.SKIP, "No API test yet", "", "Run `codex-setup test`.", "dgc_last_test_none"))
    return results
