"""pywebview ``js_api`` object: JSON-safe wrappers around ``SetupService``.

Rules: every method returns ``{"ok": bool, ...}``; exceptions become ``{"ok": False, "error":
<redacted>}``; an API key is never part of a return value; keys never go through argv.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any

from codex_setup import __version__
from codex_setup.app import SetupService
from codex_setup.core.config_store import SaveResult
from codex_setup.core.errors import CodexSetupError, ValidationError
from codex_setup.diagnostics.api_test import Outcome
from codex_setup.gui import strings as gui_strings
from codex_setup.providers.catalog import DEFAULT_MODEL, LUNOVANT
from codex_setup.security import launcher
from codex_setup.security.redact import redact, redact_config_text
from codex_setup.ui import i18n
from codex_setup.ui.i18n import tr_check, tr_step

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


def _lang_ok(lang: str | None) -> str:
    return lang if lang in _LANGS else "en"


class GuiApi:
    def __init__(self, service: SetupService | None = None, lang: str | None = None) -> None:
        self._svc = service or SetupService()
        self._lang = _lang_ok(lang or i18n.default_lang())
        self._seen: list[str] = []  # secrets typed in this process, for redaction only
        self._lock = threading.Lock()
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
            return {
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

    # -- launch / env ------------------------------------------------------
    def launch(self, target: str = "cli") -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if target == "app":
                self._svc.launch("app")
                return {"started": True}
            if target != "cli":
                raise ValidationError(f"Unknown launch target: {target!r}")
            svc = self._svc
            if svc.platform.system == "windows":
                # Own console window; the key goes through the child's environment only.
                active = svc._active()
                key = svc.get_key(active.env_key) if active.env_key else None
                if not active.env_key or not key:
                    raise CodexSetupError("No API key found for the active provider.")
                if not svc.install.cli_path:
                    raise CodexSetupError("Codex CLI was not found on PATH.")
                self._seen.append(key)
                flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
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
