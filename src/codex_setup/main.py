"""Command line entry point. No arguments opens the Rich TUI."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import traceback
from collections.abc import Callable
from typing import Any

from codex_setup import __version__
from codex_setup.app import SetupService, StatusInfo
from codex_setup.core.config_store import SaveResult
from codex_setup.core.errors import CodexSetupError, ValidationError
from codex_setup.providers.catalog import DEFAULT_MODEL, normalize_base_url, suggest_v1
from codex_setup.security.redact import mask_key, redact, redact_config_text
from codex_setup.ui.i18n import default_lang, set_lang, t, tr_check, tr_step

_SEEN_SECRETS: list[str] = []


def make_service() -> SetupService:
    return SetupService()


def _out(text: str = "") -> None:
    print(text)


def _err(text: str) -> None:
    print(text, file=sys.stderr)


def _common() -> argparse.ArgumentParser:
    """Global options, accepted before or after the subcommand."""
    p = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    p.add_argument("--codex-home", metavar="DIR", help="use DIR as CODEX_HOME for this run")
    p.add_argument("--lang", choices=["en", "vi"], help="interface language")
    p.add_argument("--yes", "-y", action="store_true", help="skip confirmations")
    p.add_argument("--dry-run", action="store_true", help="show the diff, write nothing")
    return p


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    parser = argparse.ArgumentParser(
        prog="codex-setup",
        description="Configure Codex CLI / Desktop for a third-party provider.",
        parents=[common],
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    sub = parser.add_subparsers(dest="command")

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_, parents=[common])

    add("status", "show the current setup")

    p = add("setup", "quick setup (provider + model + key)")
    p.add_argument("--base-url")
    p.add_argument("--model")
    p.add_argument("--key-stdin", action="store_true", help="read the API key from stdin")
    p.add_argument("--secret-backend", choices=["auto", "keyring", "file", "session"], default="auto")

    p = add("model", "show or change the model")
    p.add_argument("name", nargs="?")

    p = add("api", "change the base URL or the stored key")
    p.add_argument("--base-url")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--key-stdin", action="store_true")
    g.add_argument("--delete-key", action="store_true")

    p = add("test", "test the API connection")
    p.add_argument("--model")

    p = add("sandbox", "Windows sandbox mode")
    p.add_argument("mode", nargs="?", choices=["elevated", "unelevated", "remove"])

    p = add("backup", "backup operations")
    p.add_argument("action", choices=["create", "list", "restore", "original"])
    p.add_argument("id", nargs="?")

    p = add("diagnose", "run diagnostics or explain an error text")
    p.add_argument("--text")

    p = add("profile", "manage profiles")
    p.add_argument("action", choices=["list", "add", "use", "remove"])
    p.add_argument("name", nargs="?")
    p.add_argument("--base-url")
    p.add_argument("--env-key")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--models", help="comma separated list of models")

    p = add("launch", "start Codex with the key injected")
    p.add_argument("target", nargs="?", choices=["cli", "app"], default="cli")
    p.add_argument("codex_args", nargs=argparse.REMAINDER)

    p = add("env", "opt-in persistent environment variable")
    p.add_argument("action", choices=["install", "remove"])

    p = add("uninstall", "restore the original configuration")
    p.add_argument("--delete-key", action="store_true", help="also delete the stored key")
    return parser


# -- helpers -----------------------------------------------------------------
def _read_stdin_key() -> str:
    value = sys.stdin.read().strip()
    if not value:
        raise ValidationError(t("cli_key_empty"))
    _SEEN_SECRETS.append(value)
    return value


def _confirm(ns: argparse.Namespace, question: str) -> bool:
    if getattr(ns, "yes", False):
        return True
    if not sys.stdin.isatty():
        raise CodexSetupError(t("cli_confirm_noninteractive"))
    answer = input(f"{question} [y/N] ").strip().lower()
    return answer in ("y", "yes", "c", "co", "có")


def _apply(ns: argparse.Namespace, op: Callable[[bool], SaveResult | None]) -> SaveResult | None:
    """Preview with dry-run, confirm, then apply. Returns the final result."""
    if getattr(ns, "dry_run", False):
        res = op(True)
        if res is not None:
            _show_diff(res)
            _show_notes(res)
            _out(t("dry_run_done"))
        return res
    preview = op(True)
    if preview is None:
        return None
    if not preview.changed:
        _out(t("no_changes"))
        # still run for side effects such as storing a key
        return op(False)
    _show_diff(preview)
    if not _confirm(ns, t("apply_confirm")):
        _out(t("cancelled"))
        return preview
    res = op(False)
    if res is not None and res.backup:
        _out(t("applied_backup", path=res.backup))
    else:
        _out(t("applied"))
    _show_notes(res)
    return res


def _show_diff(res: SaveResult) -> None:
    if res.diff:
        # Display only: secrets and values of sensitive keys are masked; disk is untouched.
        _out(redact_config_text(res.diff, _SEEN_SECRETS).rstrip("\n"))
    else:
        _out(t("no_changes"))


def _show_notes(res: SaveResult | None) -> None:
    for key, params in (res.notes if res is not None else []):
        _out(t(key, **params))


def _session_warning(svc: SetupService, backend: str) -> None:
    try:
        name = svc.secret_store(backend).backend_name
    except CodexSetupError:
        return
    if name == "session":
        _err(t("session_warn_cli"))


def format_status(st: StatusInfo) -> list[str]:
    desk = (
        t("desktop_installed")
        if st.install.desktop_installed
        else t("desktop_missing")
        if st.install.desktop_supported
        else t("desktop_unsupported")
    )
    lt = st.last_test
    last = f"{lt.get('overall')} ({lt.get('model')}, {lt.get('when')})" if lt else t("never")
    cfg = {"ok": t("cfg_ok"), "invalid": t("cfg_invalid"), "missing": t("cfg_missing")}[st.config_state]
    lines = [
        f"{t('hdr_os')}: {st.platform.system} {st.platform.release} {st.platform.machine}",
        f"{t('hdr_cli')}: {st.install.cli_version or st.install.cli_path or t('not_found')}",
        f"{t('hdr_desktop')}: {desk}",
        f"{t('hdr_provider')}: {st.model_provider or t('none')} / {st.model or t('none')}",
        f"{t('hdr_config')}: {cfg} ({st.config_path})",
        f"{t('hdr_test')}: {last}",
        f"{t('hdr_key')}: {st.masked_key} [{st.secret_backend or t('none')}]",
    ]
    if st.config_error:
        lines.append(f"  {st.config_error}")
    return lines


# -- command handlers --------------------------------------------------------
def _cmd_status(svc: SetupService, ns: argparse.Namespace) -> int:
    for line in format_status(svc.status()):
        _out(line)
    return 0


def _resolve_url(raw: str | None) -> str | None:
    if not raw:
        return None
    url = normalize_base_url(raw)
    suggested = suggest_v1(url)
    if suggested != url:
        # No /v1: the CLI keeps a URL that already has a path, otherwise appends /v1.
        from urllib.parse import urlsplit

        if not urlsplit(url).path:
            _out(t("qs_url_note", url=suggested))
            return suggested
    return url


def _cmd_setup(svc: SetupService, ns: argparse.Namespace) -> int:
    key = _read_stdin_key() if ns.key_stdin else None
    url = _resolve_url(ns.base_url)
    model = ns.model or DEFAULT_MODEL
    if key is None and not ns.dry_run and not ns.yes and sys.stdin.isatty():
        entered = getpass.getpass(t("qs_key") + ": ").strip()
        if entered:
            _SEEN_SECRETS.append(entered)
            key = entered
    if ns.secret_backend == "file":
        _err(t("file_warn"))
        if not ns.dry_run and not _confirm(ns, t("file_confirm")):
            _out(t("cancelled"))
            return 0
    _apply(
        ns,
        lambda dry: svc.quick_setup(url, model, key, ns.secret_backend, dry),
    )
    if not ns.dry_run:
        _out(t("qs_done"))
    if key and not ns.dry_run:
        _session_warning(svc, ns.secret_backend)
    return 0


def _cmd_model(svc: SetupService, ns: argparse.Namespace) -> int:
    if not ns.name:
        st = svc.status()
        _out(f"{st.model or t('none')}")
        for m in svc.available_models():
            _out(f"  {m}")
        return 0
    _apply(ns, lambda dry: svc.change_model(ns.name, dry))
    return 0


def _cmd_api(svc: SetupService, ns: argparse.Namespace) -> int:
    key = _read_stdin_key() if ns.key_stdin else None
    url = _resolve_url(ns.base_url)
    if url is None and key is None and not ns.delete_key:
        st = svc.status()
        _out(f"{st.base_url or t('none')}  {st.env_key or ''}  {st.masked_key}")
        return 0
    _apply(ns, lambda dry: svc.set_api(url, key, ns.delete_key, dry))
    if not ns.dry_run:
        if key:
            _out(t("api_key_saved", backend=svc.secret_store().backend_name, masked=mask_key(key)))
            _session_warning(svc, svc.load_state().secret_backend or "auto")
        elif ns.delete_key:
            _out(t("api_deleted"))
    return 0


def render_report_lines(report: Any) -> list[str]:
    lines = []
    for s in report.steps:
        problem = s.problem.value if s.problem else "-"
        lines.append(f"{s.step:<18} {s.outcome.value.upper():<5} {problem:<22} {tr_step(s)}")
    lines.append(t("test_overall", overall=report.overall.value.upper()))
    return lines


def _cmd_test(svc: SetupService, ns: argparse.Namespace) -> int:
    report = svc.test(ns.model)
    for line in render_report_lines(report):
        _out(line)
    return 0 if report.overall.value == "ok" else 1


def _cmd_sandbox(svc: SetupService, ns: argparse.Namespace) -> int:
    if not svc.sandbox_applicable():
        _out(t("sb_not_applicable"))
        return 0
    if ns.mode is None:
        st = svc.status()
        _out(f"{t('status_sandbox')}: {st.windows_sandbox or t('none')}")
        return 0
    _apply(ns, lambda dry: svc.sandbox(ns.mode, dry))
    return 0


def _cmd_backup(svc: SetupService, ns: argparse.Namespace) -> int:
    if ns.action == "create":
        if ns.dry_run:
            svc.backup_create(dry_run=True)
            _out(t("dry_would_backup"))
            _out(t("dry_run_done"))
        else:
            _out(t("bk_created_ok", path=svc.backup_create()))
    elif ns.action == "list":
        items = svc.backup_list()
        if not items:
            _out(t("bk_none"))
        for info in items:
            _out(f"{info.id}  {info.created}  {info.reason}")
    elif ns.action == "restore":
        if not ns.id:
            raise ValidationError(t("cli_need_arg", name="ID"))
        _apply(ns, lambda dry: svc.backup_restore(ns.id, dry))
    else:
        _apply(ns, lambda dry: svc.backup_original(dry))
    return 0


def _cmd_diagnose(svc: SetupService, ns: argparse.Namespace) -> int:
    diag = svc.diagnose(ns.text)
    from codex_setup.ui.i18n import get_lang

    lang = get_lang()
    failed = False
    for c in diag.checks:
        title, detail, fix = tr_check(c)
        _out(f"[{c.outcome.value.upper()}] {title}")
        if detail:
            _out(f"    {detail}")
        if fix:
            _out(f"    {t('dg_fix')}: {fix}")
        failed = failed or c.outcome.value == "fail"
    for issue in diag.issues:
        _out(issue.title[lang])
        _out(issue.explanation[lang])
        for i, step in enumerate(issue.steps[lang], 1):
            _out(f"  {i}. {step}")
    if ns.text and not diag.issues:
        _out(t("dg_no_match"))
    return 1 if failed else 0


def _cmd_profile(svc: SetupService, ns: argparse.Namespace) -> int:
    if ns.action == "list":
        profiles = svc.list_profiles()
        if not profiles:
            _out(t("pf_none"))
        active = svc.load_state().active_profile
        for p in profiles:
            mark = f" ({t('pf_active')})" if p.name == active else ""
            _out(f"{p.name}{mark}  {p.provider.base_url}  {p.model}")
        return 0
    if not ns.name:
        raise ValidationError(t("cli_need_arg", name="NAME"))
    if ns.action == "add":
        models = [m.strip() for m in (ns.models or "").split(",") if m.strip()]
        svc.add_profile(ns.name, ns.base_url, ns.env_key, ns.model, models, dry_run=ns.dry_run)
        _out(t("dry_would_profile_add" if ns.dry_run else "pf_added", name=ns.name))
    elif ns.action == "use":
        _apply(ns, lambda dry: svc.use_profile(ns.name, dry))
    else:
        svc.remove_profile(ns.name, dry_run=ns.dry_run)
        _out(t("dry_would_profile_remove" if ns.dry_run else "pf_removed", name=ns.name))
    return 0


def _cmd_launch(svc: SetupService, ns: argparse.Namespace) -> int:
    args = list(ns.codex_args)
    if args and args[0] == "--":
        args = args[1:]
    if ns.target == "app":
        _out(t("ln_app_experimental"))
        svc.launch("app", args)
        _out(t("ln_app_started"))
        return 0
    return svc.launch("cli", args)


def env_warning(svc: SetupService) -> str:
    return t("env_warn_win") if svc.platform.system == "windows" else t("env_warn_posix")


def _cmd_env(svc: SetupService, ns: argparse.Namespace) -> int:
    if ns.action == "install":
        _out(env_warning(svc))
        if ns.dry_run:
            _out(t("dry_would_env_install", where=svc.env_install(True, dry_run=True)))
            _out(t("dry_run_done"))
            return 0
        if not _confirm(ns, t("env_consent")):
            _out(t("cancelled"))
            return 0
        _out(t("env_installed", where=svc.env_install(True)))
    else:
        outcome = svc.env_remove(dry_run=ns.dry_run)
        _out(
            {
                "removed": t("env_removed"),
                "restored": t("env_restored"),
                "nothing": t("env_nothing"),
                "not_owned": t("env_not_owned"),
                "changed": t("env_changed"),
            }[outcome]
        )
        if ns.dry_run:
            _out(t("dry_run_done"))
    return 0


def _cmd_uninstall(svc: SetupService, ns: argparse.Namespace) -> int:
    _out(t("un_info"))
    _apply(ns, lambda dry: svc.uninstall(dry, delete_secret=ns.delete_key))
    if not ns.dry_run:
        _out(t("un_done"))
    return 0


_HANDLERS: dict[str, Callable[[SetupService, argparse.Namespace], int]] = {
    "status": _cmd_status,
    "setup": _cmd_setup,
    "model": _cmd_model,
    "api": _cmd_api,
    "test": _cmd_test,
    "sandbox": _cmd_sandbox,
    "backup": _cmd_backup,
    "diagnose": _cmd_diagnose,
    "profile": _cmd_profile,
    "launch": _cmd_launch,
    "env": _cmd_env,
    "uninstall": _cmd_uninstall,
}


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    set_lang(getattr(ns, "lang", None) or default_lang())
    if getattr(ns, "version", False):
        _out(t("version", version=__version__))
        return 0
    if getattr(ns, "codex_home", None):
        os.environ["CODEX_HOME"] = ns.codex_home
    for name in ("yes", "dry_run"):
        if not hasattr(ns, name):
            setattr(ns, name, False)

    try:
        svc = make_service()
        if ns.command is None:
            if sys.stdin.isatty() and sys.stdout.isatty():
                from codex_setup.ui import tui

                return tui.run(svc, dry_run=ns.dry_run)
            _cmd_status(svc, ns)
            return _hint()
        return _HANDLERS[ns.command](svc, ns)
    except KeyboardInterrupt:
        _err(t("cli_cancel_sigint"))
        return 130
    except CodexSetupError as exc:
        _err(t("error", msg=redact(str(exc), _SEEN_SECRETS)))
        return 1
    except Exception as exc:  # last resort: never leak a raw traceback or secrets
        debug = os.environ.get("CODEX_SETUP_DEBUG") == "1"
        line = redact(f"{exc.__class__.__name__}: {exc}", _SEEN_SECRETS).splitlines()[0][:300]
        _err(t("err_unexpected", msg=line))
        if debug:
            _err(redact(traceback.format_exc(), _SEEN_SECRETS))
        else:
            _err(t("err_debug_hint"))
        return 1


def _hint() -> int:
    _out(t("hint_no_tty"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
