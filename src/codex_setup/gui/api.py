"""pywebview ``js_api`` object: JSON-safe wrappers around ``SetupService``.

Rules: every method returns ``{"ok": bool, ...}``; exceptions become ``{"ok": False, "error":
<redacted>}``; an API key is never part of a return value; keys never go through argv.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from collections.abc import Callable
from typing import Any

from codex_setup import __version__
from codex_setup.app import MODES, SetupService, normalize_key, suggest_v1
from codex_setup.core.config_store import SaveResult
from codex_setup.core import claude_config, codex_config
from codex_setup.core.state import load_state, save_state
from codex_setup.diagnostics import model_probe
from codex_setup.core.errors import CodexSetupError, ValidationError
from codex_setup.diagnostics.api_test import Outcome
from codex_setup.gui import strings as gui_strings
from codex_setup.providers.catalog import DEFAULT_MODEL, LUNOVANT
from codex_setup.security import launcher
from codex_setup.security.redact import redact, redact_config_text
from codex_setup.ui import i18n
from codex_setup.ui.i18n import catalog_text, tr_check, tr_step

CLAUDE_URL = "https://ai.lunovant.tech"
_LANGS = ("en", "vi")
_BACKENDS = ("auto", "keyring", "file", "session")
_PROBLEM_KEYS = {
    "bad_url": "at_bad_url",
    "dns": "at_dns",
    "tls": "at_tls",
    "network": "at_network",
    "timeout": "at_timeout",
    "unauthorized": "at_unauthorized",
    "forbidden": "at_forbidden",
    "model_not_found": "at_model_not_found",
    "rate_limited": "at_rate_limited",
    "responses_unsupported": "at_responses_unsupported",
    "server_error": "at_server_error",
    "incompatible": "at_incompatible",
    "unknown": "at_unknown",
}


def _norm_url(url: Any) -> str:
    return str(url or "").strip().rstrip("/")


def _lang_ok(lang: str | None) -> str:
    return lang if lang in _LANGS else "en"


class GuiApi:
    def __init__(self, service: SetupService | None = None, lang: str | None = None) -> None:
        self._svc = service or SetupService()
        self._lang = _lang_ok(lang or i18n.default_lang())
        self._seen: list[str] = []  # secrets typed in this process, for redaction only
        self._lock = threading.Lock()
        self._oc_lock = threading.Lock()  # guards the one-click run state below
        self._oc: dict[str, Any] = {"running": False, "steps": [], "result": None, "run": 0}
        i18n.set_lang(self._lang)

    # -- plumbing ----------------------------------------------------------
    def _guard(self, fn: Callable[[], dict[str, Any]], *secrets: str | None) -> dict[str, Any]:
        for s in secrets:
            if s:
                self._seen.append(s.strip())
        try:
            with self._lock:
                out = fn()
            out.setdefault("ok", True)
            return out
        except CodexSetupError as exc:
            return {"ok": False, "error": redact(str(exc), self._seen)}
        except Exception as exc:  # never leak raw tracebacks or secrets to the page
            msg = f"{exc.__class__.__name__}: {exc}"
            return {"ok": False, "error": redact(msg, self._seen)[:300]}

    def _diff(self, res: SaveResult | None) -> dict[str, Any]:
        if res is None:
            return {"changed": False, "diff": "", "backup": None, "notes": []}
        text = redact_config_text(res.diff or "", self._seen)
        return {
            "changed": bool(res.changed),
            "diff": text,
            "backup": str(res.backup) if res.backup else None,
            "notes": [i18n.t(k, **p) for k, p in res.notes],
            "dry_run": bool(res.dry_run),
        }

    @staticmethod
    def _backend(value: str | None) -> str:
        value = value or "auto"
        if value not in _BACKENDS:
            raise ValidationError(f"Unsupported secret backend: {value!r}")
        return value

    # -- read-only ---------------------------------------------------------
    def status(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            st = self._svc.status()
            mode, installed = None, False
            if st.config_state == "ok":
                mode = self._svc.current_mode()
                installed = LUNOVANT.id in st.provider_ids and (
                    self._svc.ownership().managed_provider_ids != []
                    or load_state(self._svc._env).one_click is not None
                )
            return {
                "claude": self._claude_status(),
                "chatgpt_login": self._svc.chatgpt_login_present(),
                "mode": mode,
                "lunovant_installed": installed,
                "version": __version__,
                "os": {
                    "system": st.platform.system,
                    "release": st.platform.release,
                    "machine": st.platform.machine,
                },
                "cli": {
                    "path": st.install.cli_path,
                    "version": st.install.cli_version,
                },
                "desktop": {
                    "supported": st.install.desktop_supported,
                    "installed": st.install.desktop_installed,
                    "note": st.install.desktop_note,
                },
                "config": {
                    "path": str(st.config_path),
                    "state": st.config_state,
                    "error": redact(st.config_error or "", self._seen) or None,
                },
                "provider": st.model_provider,
                "model": st.model,
                "base_url": st.base_url,
                "env_key": st.env_key,
                "masked_key": st.masked_key,
                "secret_backend": st.secret_backend,
                "last_test": st.last_test,
                "windows_sandbox": st.windows_sandbox,
                "is_windows": st.platform.system == "windows",
                "default_base_url": LUNOVANT.base_url,
                "default_model": DEFAULT_MODEL,
            }

        return self._guard(run)

    def _claude_status(self) -> dict[str, Any]:
        svc = self._svc
        installed = svc.claude_installed()
        mode = svc.claude_current_mode() if installed else None
        return {
            "installed": installed,
            "mode": mode,
            "login": svc.claude_login_present(),
            "cli_path": shutil.which("claude"),
            "terminal": launcher.terminal_supported(svc.platform.system),
            "command": svc.claude_launch_command(mode),
            "profile_command": svc.claude_profile_command(),
            "settings_path": str(svc.claude_settings_path),
            "profile_path": str(svc.claude_profile_path),
        }

    def _gt(self, key: str) -> str:
        return (gui_strings.VI if self._lang == "vi" else gui_strings.EN)[key]

    def strings(self, lang: str | None = None) -> dict[str, Any]:
        lang = _lang_ok(lang)
        self._lang = lang
        i18n.set_lang(lang)
        table = dict(i18n.EN)
        table.update(gui_strings.EN)
        if lang != "en":
            table.update(i18n._TABLES[lang])
            table.update(getattr(gui_strings, lang.upper()))
        return {"ok": True, "lang": lang, "strings": table}

    def default_lang(self) -> dict[str, Any]:
        return {"ok": True, "lang": self._lang}

    def models(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            custom = self._svc.custom_models()
            return {
                "models": self._svc.available_models() or [DEFAULT_MODEL],
                "custom": custom,
                "default": DEFAULT_MODEL,
            }

        return self._guard(run)

    # -- setup -------------------------------------------------------------
    def preview_setup(self, base_url: str | None, model: str) -> dict[str, Any]:
        return self._guard(
            lambda: self._diff(self._svc.quick_setup(base_url or None, model, None, "auto", True))
        )

    def quick_setup(
        self,
        base_url: str | None,
        model: str,
        api_key: str | None,
        secret_backend: str = "auto",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            backend = self._backend(secret_backend)
            res = self._svc.quick_setup(base_url or None, model, api_key or None, backend, dry_run)
            out = self._diff(res)
            if not dry_run and api_key:
                out["backend"] = self._svc.secret_store(backend).backend_name
            return out

        return self._guard(run, api_key)

    def change_model(self, model: str, dry_run: bool = False) -> dict[str, Any]:
        return self._guard(lambda: self._diff(self._svc.change_model(model, dry_run)))

    def set_api(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        delete_key: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            res = self._svc.set_api(base_url or None, api_key or None, bool(delete_key), dry_run)
            out = self._diff(res)
            if not dry_run and api_key:
                out["backend"] = self._svc.secret_store().backend_name
            return out

        return self._guard(run, api_key)

    # -- test --------------------------------------------------------------
    def test_connection(self, model: str | None = None) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            report = self._svc.test(model or None)
            steps = []
            for s in report.steps:
                problem = ""
                if s.problem is not None:
                    key = _PROBLEM_KEYS.get(s.problem.value)
                    problem = i18n.t(key, http=s.http_status or "") if key else s.problem.value
                steps.append(
                    {
                        "step": s.step,
                        "outcome": s.outcome.value,
                        "problem": s.problem.value if s.problem else None,
                        "problem_text": problem,
                        "detail_text": redact(tr_step(s), self._seen),
                    }
                )
            overall = report.overall
            return {
                "steps": steps,
                "overall": overall.value,
                "success": overall == Outcome.OK,
            }

        return self._guard(run)

    # -- sandbox -----------------------------------------------------------
    def sandbox_options(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not self._svc.sandbox_applicable():
                return {"applicable": False, "current": None, "explanation": "", "modes": []}
            st = self._svc.status()
            return {
                "applicable": True,
                "current": st.windows_sandbox,
                "explanation": i18n.t("sb_explain"),
                "recommended": "unelevated",
                "modes": ["unelevated", "elevated"],
            }

        return self._guard(run)

    def set_sandbox(self, mode: str | None, dry_run: bool = False) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if mode not in (None, "elevated", "unelevated"):
                raise ValidationError(f"Unsupported sandbox mode: {mode!r}")
            if not self._svc.sandbox_applicable():
                return {"ok": False, "error": i18n.t("sb_not_applicable")}
            return self._diff(self._svc.sandbox(mode, dry_run))

        return self._guard(run)

    # -- backups -----------------------------------------------------------
    def backups(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            items = [
                {"id": b.id, "created": b.created, "reason": b.reason, "size": b.size}
                for b in self._svc.backup_list()
            ]
            return {"backups": items, "has_original": bool(self._svc.ownership().original_snapshot)}

        return self._guard(run)

    def create_backup(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            path = self._svc.backup_create()
            return {"path": str(path) if path else None}

        return self._guard(run)

    def restore_backup(self, backup_id: str, dry_run: bool = False) -> dict[str, Any]:
        return self._guard(lambda: self._diff(self._svc.backup_restore(backup_id, dry_run)))

    def restore_original(self, dry_run: bool = False) -> dict[str, Any]:
        return self._guard(lambda: self._diff(self._svc.backup_original(dry_run)))

    # -- diagnostics -------------------------------------------------------
    def diagnose(self, text: str | None = None) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            diag = self._svc.diagnose((text or "").strip() or None)
            lang = self._lang
            checks = []
            for c in diag.checks:
                title, detail, fix = tr_check(c)
                checks.append(
                    {
                        "outcome": c.outcome.value,
                        "title": title,
                        "detail": redact(detail, self._seen),
                        "fix": fix,
                    }
                )
            issues = [
                {
                    "id": i.id,
                    "title": i.title[lang],
                    "explanation": i.explanation[lang],
                    "steps": list(i.steps[lang]),
                }
                for i in diag.issues
            ]
            return {"checks": checks, "issues": issues}

        return self._guard(run)

    # -- one-click setup ---------------------------------------------------
    def _scrub(self, obj: Any) -> Any:
        """Recursively redact typed secrets from anything sent to the page."""
        if isinstance(obj, str):
            return redact(obj, self._seen)
        if isinstance(obj, list):
            return [self._scrub(x) for x in obj]
        if isinstance(obj, dict):
            return {str(k): self._scrub(v) for k, v in obj.items()}
        return obj

    @staticmethod
    def _section(res: Any) -> dict[str, Any]:
        """JSON view of one line's result (no key anywhere)."""
        out: dict[str, Any] = {
            "ok": bool(res.ok),
            "line": res.line,
            "code": res.code,
            "message": res.message,
            "key_info": res.key_info,
            "models": res.models,
            "default_model": res.default_model,
            "has_backup": bool(res.backup_path),
            "mode": res.mode,
            "legacy_profile": res.legacy_profile,
        }
        if res.line == "claude":
            out["claude_models"] = res.claude_models
        elif res.catalog:
            out["catalog"] = res.catalog
            out["catalog_text"] = catalog_text(res.catalog)
        return out

    def detect_lines(
        self, key: str | None = None, base_url: str | None = None, *, client: Any = None
    ) -> dict[str, Any]:
        """Which lines a key covers, from ``GET {base}/models`` only (``gpt-*`` = codex,
        ``claude-*`` = claude). Writes nothing, stores nothing, returns no key."""

        def run() -> dict[str, Any]:
            k = normalize_key(key)
            if not k:
                return {"ok": False, "error_code": "key_empty"}
            if not (k.isascii() and k.isprintable()):
                return {"ok": False, "error_code": "key_invalid"}
            url = suggest_v1(base_url) if base_url else LUNOVANT.base_url
            http = {"client": client} if client is not None else {}
            models, err = model_probe.fetch_models_checked(url, k, **http)
            if err:
                return {"ok": False, "error_code": err}
            lines = [n for n, on in (
                ("codex", any(m.startswith("gpt-") for m in models)),
                ("claude", any(claude_config.is_claude_model(m) for m in models)),
            ) if on]
            if not lines:
                return {"ok": False, "error_code": "not_codex_key"}
            return {"ok": True, "lines": lines}

        return self._scrub(self._guard(run, key))

    def one_click_start(
        self, key: str | None = None, mode: str = "lunovant", claude_mode: str | None = None
    ) -> dict[str, Any]:
        claude_mode = claude_mode or mode
        if mode not in MODES or claude_mode not in MODES:
            return {"ok": False, "error": f"Unsupported mode: {mode!r}"}
        if not self._svc.chatgpt_login_present():
            mode = "lunovant"  # nothing personal to keep: no question, no choice
        if not self._svc.claude_login_present():
            claude_mode = "lunovant"
        key = (key or "").strip()
        if key:
            self._seen.append(key)
        with self._oc_lock:
            if self._oc["running"]:
                return {"ok": False, "error": "busy", "busy": True}
            # ctx (key + endpoint of this run) stays in backend memory for re-probes; never sent out
            self._oc = {"running": True, "steps": [], "result": None, "run": self._oc["run"] + 1,
                        "ctx": {"key": key, "url": LUNOVANT.base_url}}
            run = self._oc["run"]

        def progress(step: str, detail: dict[str, Any]) -> None:
            with self._oc_lock:
                if self._oc["run"] == run:
                    self._oc["steps"].append({"step": step, "detail": self._scrub(detail)})

        def work() -> None:
            try:
                with self._lock:  # same lock as every other config/state-changing API call
                    res = self._svc.one_click_setup(
                        key, None, progress, mode=mode, claude_mode=claude_mode)
                result: dict[str, Any] = self._section(res)
                result["sections"] = {
                    name: self._section(part) for name, part in res.sections.items()
                }
            except Exception as exc:  # never leak raw tracebacks or secrets
                msg = redact(f"{exc.__class__.__name__}: {exc}", self._seen)[:300]
                result = {"ok": False, "code": "error", "message": msg, "key_info": None,
                          "models": [], "default_model": None, "has_backup": False,
                          "sections": {}}
            with self._oc_lock:
                if self._oc["run"] == run:
                    self._oc["result"] = self._scrub(result)
                    self._oc["running"] = False

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "started": True}

    def one_click_poll(self) -> dict[str, Any]:
        with self._oc_lock:
            return {
                "ok": True,
                "running": bool(self._oc["running"]),
                "steps": list(self._oc["steps"]),
                "result": self._oc["result"],
            }

    def one_click_last(self) -> dict[str, Any]:
        """Last saved one-click result per line. Codex only while its bearer provider is still
        active; Claude only while its profile file and settings record are still there."""

        def run() -> dict[str, Any]:
            sections: dict[str, Any] = {}
            state = load_state(self._svc._env)
            saved = state.one_click
            active = self._svc._active(ours=True)
            if (
                saved
                and (active.table or {}).get(codex_config.BEARER_FIELD)
                and _norm_url(saved.get("base_url")) == _norm_url(active.base_url)
            ):
                sections["codex"] = {
                    "when": saved.get("when"),
                    "key_info": saved.get("key_info"),
                    "models": [m for m in saved.get("models") or []
                               if not model_probe.is_excluded_model(str(m))],
                    "results": [r for r in saved.get("results") or []
                                if not (isinstance(r, dict)
                                        and model_probe.is_excluded_model(str(r.get("model", ""))))],
                    "default_model": saved.get("default_model"),
                    "current_model": active.model,
                }
            crec = state.claude or {}
            coc = crec.get("one_click")
            prof = claude_config.read_profile_env(self._svc.claude_profile_path)
            if coc and prof and self._svc.claude_installed() and \
                    _norm_url(coc.get("base_url")) == _norm_url(prof.get("ANTHROPIC_BASE_URL")):
                sections["claude"] = {
                    "when": coc.get("when"),
                    "key_info": coc.get("key_info"),
                    "models": list(coc.get("models") or []),
                    "results": list(coc.get("results") or []),
                    "default_model": coc.get("default_model"),
                    "current_model": prof.get("ANTHROPIC_MODEL"),
                }
            if not sections:
                return {"has_last": False}
            first = sections.get("codex") or sections["claude"]
            return self._scrub({"has_last": True, **first, "sections": sections})

        return self._guard(run)

    def set_mode(self, mode: str, dry_run: bool = False, line: str = "codex") -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if line == "claude":
                if mode == "personal" and not self._svc.claude_login_present():
                    raise ValidationError(self._gt("g_claude_mode_no_login"))
                out = self._diff(self._svc.claude_set_mode(mode, bool(dry_run)))
                out["mode"] = mode if not dry_run else self._svc.claude_current_mode()
                return out
            if line != "codex":
                raise ValidationError(f"Unknown line: {line!r}")
            if mode == "personal" and not self._svc.chatgpt_login_present():
                raise ValidationError(i18n.t("g_mode_no_login"))
            out = self._diff(self._svc.set_mode(mode, bool(dry_run)))
            out["mode"] = mode if not dry_run else self._svc.current_mode()
            return out

        return self._guard(run)

    def set_default_model(self, model: str) -> dict[str, Any]:
        return self._guard(lambda: self._diff(self._svc.set_default_model(model)))

    def _reprobe_claude(self, model_: str) -> dict[str, Any]:
        svc = self._svc
        with self._oc_lock:
            if self._oc["running"]:
                raise CodexSetupError("A setup is already running.")
            ctx = self._oc.get("ctx")
        prof = claude_config.read_profile_env(svc.claude_profile_path)
        if not prof:
            raise CodexSetupError("Lunovant for Claude Code is not set up yet. Run the setup first.")
        key = str((ctx or {}).get("key") or prof["ANTHROPIC_AUTH_TOKEN"])
        url = prof["ANTHROPIC_BASE_URL"]
        self._seen.append(key)
        res = model_probe.probe_claude_models(url, key, [model_])[0]
        if key == prof["ANTHROPIC_AUTH_TOKEN"]:
            state = load_state(svc._env)  # fresh: never write back a stale snapshot
            oc = (state.claude or {}).get("one_click")
            if oc is not None:
                rows = [r for r in oc.get("results", []) if isinstance(r, dict)]
                old = next((r for r in rows if r.get("model") == model_), None)
                if old is not None and old.get("role"):
                    res["role"] = old["role"]
                rows = [res if r.get("model") == model_ else r for r in rows]
                if old is None:
                    rows.append(res)
                oc["results"] = rows
                save_state(state, svc._env)
        return {"result": self._scrub(res)}

    def reprobe_model(self, model: str, line: str = "codex") -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if line == "claude":
                m = (model or "").strip()
                if not m:
                    raise ValidationError("Model name is empty.")
                return self._reprobe_claude(m)
            model_ = (model or "").strip()
            if not model_:
                raise ValidationError("Model name is empty.")
            if model_probe.is_excluded_model(model_):
                raise ValidationError("This model is not a chat model and is not tested.")
            svc = self._svc
            with self._oc_lock:
                if self._oc["running"]:
                    raise CodexSetupError("A setup is already running.")
                ctx = self._oc.get("ctx")
                oc_result = self._oc.get("result")
            active = svc._active(ours=True)
            bearer = (active.table or {}).get(codex_config.BEARER_FIELD)
            persist = False
            if ctx and oc_result is not None:
                # Re-probe the run that is on screen with that run's own key and endpoint.
                key, url = str(ctx["key"]), str(ctx["url"])
                persist = bool(
                    oc_result.get("ok") and bearer == key
                    and _norm_url(active.base_url) == _norm_url(url)
                )
            else:
                # Result restored from disk: only valid for the still-active provider/endpoint.
                saved0 = load_state(svc._env).one_click or {}
                if not bearer or _norm_url(saved0.get("base_url")) != _norm_url(active.base_url):
                    raise CodexSetupError("The saved setup result is out of date. Run setup again.")
                key, url, persist = str(bearer), str(active.base_url), True
            self._seen.append(key)
            res = model_probe.probe_models(url, key, [model_])[0]
            if persist:
                state = load_state(svc._env)  # fresh: never write back a stale snapshot
                saved = state.one_click
                if saved is not None and _norm_url(saved.get("base_url")) == _norm_url(url):
                    rows = [r for r in saved.get("results", []) if isinstance(r, dict)]
                    if any(r.get("model") == model_ for r in rows):
                        rows = [res if r.get("model") == model_ else r for r in rows]
                    else:
                        rows.append(res)
                    saved["results"] = rows
                    save_state(state, svc._env)
            return {"result": self._scrub(res)}

        return self._guard(run)

    def open_url(self, url: str) -> dict[str, Any]:
        if url != CLAUDE_URL:
            return {"ok": False, "error": "URL not allowed"}
        try:
            webbrowser.open(url)
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}
        return {"ok": True}

    # -- launch / env ------------------------------------------------------
    def launch(self, target: str = "cli") -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if target == "claude":
                svc0 = self._svc
                # macOS: the GUI's PATH often lacks ~/.local/bin or npm/nvm dirs; Terminal's
                # login shell resolves `claude` itself, so do not block on our own lookup.
                if svc0.platform.system != "macos" and not shutil.which("claude"):
                    raise CodexSetupError(self._gt("g_claude_not_found"))
                argv = ["claude"]
                if svc0.claude_current_mode() != "lunovant":
                    argv += ["--settings", str(svc0.claude_profile_path)]
                launcher.open_terminal(svc0.platform.system, argv)
                return {"started": True}
            if target == "app":
                self._svc.launch("app")
                return {"started": True}
            if target != "cli":
                raise ValidationError(f"Unknown launch target: {target!r}")
            svc = self._svc
            if svc.platform.system == "windows":
                # Own console window. A bearer-token provider needs no env var at all; an
                # env_key provider gets the key through the child's environment only.
                active = svc._active()
                table = active.table or {}
                bearer = table.get(codex_config.BEARER_FIELD)
                if not svc.install.cli_path:
                    raise CodexSetupError("Codex CLI was not found on PATH.")
                flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                if bearer and not table.get("env_key"):
                    self._seen.append(str(bearer))
                    subprocess.Popen(  # noqa: S603
                        [svc.install.cli_path], env=dict(os.environ), creationflags=flags
                    )
                    return {"started": True}
                key = (svc.get_key(active.env_key) if active.env_key else None) or bearer
                if not active.env_key or not key:
                    raise CodexSetupError("No API key found for the active provider.")
                self._seen.append(key)
                subprocess.Popen(  # noqa: S603
                    [svc.install.cli_path],
                    env=launcher.build_env(os.environ, active.env_key, key),
                    creationflags=flags,
                )
                return {"started": True}
            if not (sys.stdin and sys.stdin.isatty()):
                table = gui_strings.VI if self._lang == "vi" else gui_strings.EN
                raise CodexSetupError(table["g_cli_needs_terminal"])
            threading.Thread(target=svc.launch, args=("cli",), daemon=True).start()
            return {"started": True}

        return self._guard(run)

    def env_install(self, consent: bool = False) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            return {"where": self._svc.env_install(bool(consent))}

        return self._guard(run)

    def env_remove(self) -> dict[str, Any]:
        return self._guard(lambda: {"result": self._svc.env_remove()})

    # -- uninstall ---------------------------------------------------------
    def uninstall(self, delete_key: bool = False, dry_run: bool = False) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            res = self._svc.uninstall(dry_run, delete_secret=bool(delete_key))
            return self._diff(res)

        return self._guard(run)


__all__ = ["GuiApi"]
