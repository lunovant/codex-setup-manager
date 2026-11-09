"""Rich menu UI. Plain console output only (no alt-screen), safe on Windows Terminal / cmd."""

from __future__ import annotations

import getpass
import sys
from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.syntax import Syntax
from rich.table import Table

from codex_setup.app import SetupService, StatusInfo
from codex_setup.core.config_store import SaveResult
from codex_setup.core.errors import CodexSetupError
from codex_setup.providers.catalog import (
    DEFAULT_MODEL,
    LUNOVANT,
    LUNOVANT_MODELS,
    normalize_base_url,
    suggest_v1,
)
from codex_setup.security.redact import mask_key, redact, redact_config_text
from codex_setup.ui.i18n import t, tr_check, tr_step

_OUTCOME_STYLE = {"ok": "green", "warn": "yellow", "fail": "red", "skip": "dim"}


def _make_console() -> Console:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    return Console()


class TuiApp:
    def __init__(self, svc: SetupService, console: Console, dry_run: bool = False) -> None:
        self.svc = svc
        self.c = console
        self.dry_run = dry_run
        self.secrets: list[str] = []

    # -- plumbing ----------------------------------------------------------
    def say(self, text: str, style: str | None = None) -> None:
        self.c.print(redact(text, self.secrets), style=style, markup=False, highlight=False)

    def hidden(self, prompt: str) -> str:
        value = getpass.getpass(prompt + ": ").strip()
        if value:
            self.secrets.append(value)
        return value

    def show_diff(self, diff: str) -> None:
        shown = redact_config_text(diff, self.secrets)  # display only; disk is untouched
        self.c.print(Panel(Syntax(shown, "diff", theme="ansi_dark"), title=t("diff_title")))

    def show_notes(self, res: SaveResult | None) -> None:
        for key, params in (res.notes if res is not None else []):
            self.say(t(key, **params))

    def apply(self, op: Callable[[bool], SaveResult | None]) -> SaveResult | None:
        """Preview -> diff -> Confirm -> apply (or just preview when dry-run is on)."""
        preview = op(True)
        if preview is None:
            return None
        if not preview.changed:
            self.say(t("no_changes"))
            return op(False) if not self.dry_run else preview
        self.show_diff(preview.diff)
        if self.dry_run:
            self.show_notes(preview)
            self.say(t("dry_run_done"), "yellow")
            return preview
        if not Confirm.ask(t("apply_confirm"), default=True, console=self.c):
            self.say(t("cancelled"))
            return preview
        res = op(False)
        if res is not None and res.backup:
            self.say(t("applied_backup", path=res.backup), "green")
        else:
            self.say(t("applied"), "green")
        self.show_notes(res)
        return res

    def _dry_note(self, key: str, **params: str) -> None:
        if self.dry_run:
            self.say(t(key, **params), "yellow")
            self.say(t("dry_run_done"), "yellow")

    def guarded(self, fn: Callable[[], Any]) -> None:
        try:
            fn()
        except CodexSetupError as exc:
            self.say(t("error", msg=str(exc)), "red")

    # -- header / menu -----------------------------------------------------
    def header(self, st: StatusInfo) -> Panel:
        inst = st.install
        if inst.desktop_installed:
            desk = f"{t('desktop_installed')} - {inst.desktop_note}"
        elif inst.desktop_supported:
            desk = f"{t('desktop_missing')} - {inst.desktop_note}"
        else:
            desk = f"{t('desktop_unsupported')} - {inst.desktop_note}"
        lt = st.last_test
        last = f"{str(lt.get('overall')).upper()} ({lt.get('model')}, {lt.get('when')})" if lt else t("never")
        cfg = {"ok": t("cfg_ok"), "invalid": t("cfg_invalid"), "missing": t("cfg_missing")}[st.config_state]
        table = Table.grid(padding=(0, 2))
        rows = [
            (t("hdr_os"), f"{st.platform.system} {st.platform.release} {st.platform.machine}"),
            (t("hdr_cli"), inst.cli_version or inst.cli_path or t("not_found")),
            (t("hdr_desktop"), desk),
            (t("hdr_provider"), f"{st.model_provider or t('none')} / {st.model or t('none')}"),
            (t("hdr_config"), cfg),
            (t("hdr_test"), last),
            (t("hdr_key"), f"{st.masked_key} [{st.secret_backend or t('none')}]"),
        ]
        for k, v in rows:
            table.add_row(k, v)
        return Panel(table, title=t("app_title"))

    def menu_items(self) -> list[tuple[str, str]]:
        items = [(str(i), t(f"menu_{i}")) for i in (1, 2, 3, 4)]
        if self.svc.sandbox_applicable():
            items.append(("5", t("menu_5")))
        items += [(str(i), t(f"menu_{i}")) for i in (6, 7, 8, 9)]
        items += [("L", t("menu_L")), ("D", t("menu_D")), ("0", t("menu_0"))]
        return items

    def loop(self) -> int:
        actions: dict[str, Callable[[], None]] = {
            "1": self.quick_setup,
            "2": self.change_model,
            "3": self.api_settings,
            "4": self.test_connection,
            "5": self.sandbox,
            "6": self.backups,
            "7": self.diagnostics,
            "8": self.profiles,
            "9": self.uninstall,
            "L": self.launch,
        }
        while True:
            st = self.svc.status()
            self.c.print(self.header(st))
            if self.dry_run:
                self.say(t("dry_run_on"), "yellow")
            items = self.menu_items()
            for key, label in items:
                self.say(f"  {key}) {label}")
            choice = Prompt.ask(t("menu_choice"), console=self.c).strip().upper()
            if choice == "0":
                self.say(t("bye"))
                return 0
            if choice == "D":
                self.dry_run = not self.dry_run
                continue
            if choice not in dict(items) or choice not in actions:
                self.say(t("invalid_choice"), "red")
                continue
            self.guarded(actions[choice])

    # -- screens -----------------------------------------------------------
    def quick_setup(self) -> None:
        url = Prompt.ask(t("qs_base_url"), default=LUNOVANT.base_url, console=self.c).strip()
        normalized = normalize_base_url(url)
        suggested = suggest_v1(normalized)
        if suggested != normalized and Confirm.ask(
            t("qs_url_no_path", url=suggested), default=True, console=self.c
        ):
            normalized = suggested
        model = Prompt.ask(t("qs_model"), default=DEFAULT_MODEL, console=self.c).strip()
        key = self.hidden(t("qs_key")) or None
        backend = Prompt.ask(
            t("qs_backend"), choices=["auto", "session", "file"], default="auto", console=self.c
        )
        if backend == "file":
            self.say(t("file_warn"), "red")
            if not self.dry_run and not Confirm.ask(t("file_confirm"), default=False, console=self.c):
                self.say(t("cancelled"))
                return
        self.apply(lambda dry: self.svc.quick_setup(normalized, model, key, backend, dry))
        if not self.dry_run:
            self.say(t("qs_done"), "green")
            if key and self.svc.secret_store(backend).backend_name == "session":
                self.say(t("qs_session_warn"), "yellow")

    def _model_table(self, names: list[str], current: str | None) -> Table:
        table = Table(title=t("model_title"))
        table.add_column("#")
        table.add_column(t("model_name"))
        table.add_column("")
        custom = set(self.svc.custom_models())
        for i, name in enumerate(names, 1):
            tags = []
            if name == DEFAULT_MODEL:
                tags.append(t("model_default"))
            if name in custom and name not in LUNOVANT_MODELS:
                tags.append(t("model_custom"))
            if name == current:
                tags.append("*")
            table.add_row(str(i), name, ", ".join(tags))
        return table

    def change_model(self) -> None:
        while True:
            names = self.svc.available_models()
            st = self.svc.status()
            self.c.print(self._model_table(names, st.model))
            raw = Prompt.ask(t("model_pick"), console=self.c).strip()
            low = raw.upper()
            if raw in ("", "0"):
                return
            if low == "A":
                self.svc.add_custom_model(Prompt.ask(t("model_name"), console=self.c), self.dry_run)
                self._dry_note("dry_would_model")
                continue
            if low == "E":
                old = Prompt.ask(t("model_old"), console=self.c)
                self.svc.edit_custom_model(old, Prompt.ask(t("model_name"), console=self.c), self.dry_run)
                self._dry_note("dry_would_model")
                continue
            if low == "R":
                self.svc.remove_custom_model(Prompt.ask(t("model_old"), console=self.c), self.dry_run)
                self._dry_note("dry_would_model")
                continue
            if raw.isdigit() and 1 <= int(raw) <= len(names):
                model = names[int(raw) - 1]
                self.apply(lambda dry: self.svc.change_model(model, dry))
                return
            self.say(t("invalid_choice"), "red")

    def api_settings(self) -> None:
        self.say(t("api_menu"))
        choice = IntPrompt.ask(t("menu_choice"), choices=["0", "1", "2", "3"], console=self.c)
        if choice == 1:
            url = Prompt.ask(t("api_url"), console=self.c).strip()
            normalized = normalize_base_url(url)
            suggested = suggest_v1(normalized)
            if suggested != normalized and Confirm.ask(
                t("qs_url_no_path", url=suggested), default=True, console=self.c
            ):
                normalized = suggested
            self.apply(lambda dry: self.svc.set_api(base_url=normalized, dry_run=dry))
        elif choice == 2:
            key = self.hidden(t("api_key"))
            if key:
                if self.dry_run:
                    self.svc.set_api(api_key=key, dry_run=True)
                    self._dry_note("dry_would_key_set")
                    return
                self.svc.set_api(api_key=key)
                self.say(
                    t("api_key_saved", backend=self.svc.secret_store().backend_name, masked=mask_key(key)),
                    "green",
                )
        elif choice == 3:
            if self.dry_run:
                self.svc.set_api(delete_key=True, dry_run=True)
                self._dry_note("dry_would_key_delete")
            elif Confirm.ask(t("api_delete_confirm"), default=False, console=self.c):
                self.svc.set_api(delete_key=True)
                self.say(t("api_deleted"), "green")

    def render_report(self, report: Any) -> None:
        table = Table(title=t("test_title"))
        for col in ("test_step", "test_result", "test_problem", "test_detail"):
            table.add_column(t(col), overflow="fold")
        for s in report.steps:
            style = _OUTCOME_STYLE.get(s.outcome.value, "")
            table.add_row(
                s.step,
                f"[{style}]{s.outcome.value.upper()}[/{style}]" if style else s.outcome.value.upper(),
                s.problem.value if s.problem else "-",
                redact(tr_step(s), self.secrets),
            )
        self.c.print(table)
        self.say(t("test_overall", overall=report.overall.value.upper()))

    def test_connection(self) -> None:
        model = Prompt.ask(t("test_model"), default="", console=self.c).strip() or None
        st = self.svc.status()
        self.say(t("test_running", url=st.base_url or "-", model=model or st.model or DEFAULT_MODEL))
        self.render_report(self.svc.test(model))

    def sandbox(self) -> None:
        if not self.svc.sandbox_applicable():
            self.say(t("sb_not_applicable"))
            return
        self.say(t("sb_explain"))
        self.say(t("sb_menu"))
        choice = IntPrompt.ask(t("menu_choice"), choices=["0", "1", "2", "3"], console=self.c)
        mode = {1: "unelevated", 2: "elevated", 3: "remove"}.get(choice)
        if mode:
            self.apply(lambda dry: self.svc.sandbox(mode, dry))

    def backups(self) -> None:
        items = self.svc.backup_list()
        if items:
            table = Table(title=t("bk_title"))
            for col in ("bk_id", "bk_created", "bk_reason"):
                table.add_column(t(col))
            for info in items[:20]:
                table.add_row(info.id, info.created, info.reason)
            self.c.print(table)
        else:
            self.say(t("bk_none"))
        self.say(t("bk_menu"))
        choice = IntPrompt.ask(t("menu_choice"), choices=["0", "1", "2", "3"], console=self.c)
        if choice == 1:
            if self.dry_run:
                self.svc.backup_create(dry_run=True)
                self._dry_note("dry_would_backup")
            else:
                self.say(t("bk_created_ok", path=self.svc.backup_create()))
        elif choice == 2:
            bid = Prompt.ask(t("bk_pick"), default=items[0].id if items else "", console=self.c)
            self.apply(lambda dry: self.svc.backup_restore(bid, dry))
        elif choice == 3:
            self.apply(lambda dry: self.svc.backup_original(dry))

    def diagnostics(self) -> None:
        self.say(t("dg_menu"))
        choice = IntPrompt.ask(t("menu_choice"), choices=["0", "1", "2"], console=self.c)
        if choice == 0:
            return
        from codex_setup.ui.i18n import get_lang

        lang = get_lang()
        if choice == 1:
            diag = self.svc.diagnose(None)
            table = Table(title=t("dg_title"))
            table.add_column(t("dg_check"))
            table.add_column(t("test_result"))
            table.add_column(t("test_detail"), overflow="fold")
            table.add_column(t("dg_fix"), overflow="fold")
            for r in diag.checks:
                title, detail, fix = tr_check(r)
                table.add_row(title, r.outcome.value.upper(), redact(detail, self.secrets), fix)
            self.c.print(table)
            return
        text = Prompt.ask(t("dg_paste"), console=self.c)
        diag = self.svc.diagnose(text)
        if not diag.issues:
            self.say(t("dg_no_match"))
        for issue in diag.issues:
            self.say(issue.title[lang], "bold")
            self.say(issue.explanation[lang])
            for i, step in enumerate(issue.steps[lang], 1):
                self.say(f"  {i}. {step}")

    def profiles(self) -> None:
        profs = self.svc.list_profiles()
        active = self.svc.load_state().active_profile
        if profs:
            table = Table(title=t("pf_title"))
            for col in ("pf_name_col", "pf_url_col", "pf_model_col"):
                table.add_column(t(col))
            for p in profs:
                mark = f" ({t('pf_active')})" if p.name == active else ""
                table.add_row(p.name + mark, p.provider.base_url, p.model)
            self.c.print(table)
        else:
            self.say(t("pf_none"))
        self.say(t("pf_menu"))
        choice = IntPrompt.ask(t("menu_choice"), choices=["0", "1", "2", "3"], console=self.c)
        if choice == 1:
            name = Prompt.ask(t("pf_pick"), console=self.c).strip()
            self.apply(lambda dry: self.svc.use_profile(name, dry))
        elif choice == 2:
            name = Prompt.ask(t("pf_name"), console=self.c).strip()
            url = env_key = None
            if name != "openai":
                url = Prompt.ask(t("pf_url"), console=self.c).strip()
                env_key = Prompt.ask(t("pf_env_key"), console=self.c).strip()
            model = Prompt.ask(t("pf_model"), default=DEFAULT_MODEL, console=self.c).strip()
            self.svc.add_profile(name, url, env_key, model, dry_run=self.dry_run)
            if self.dry_run:
                self._dry_note("dry_would_profile_add", name=name)
            else:
                self.say(t("pf_added", name=name), "green")
        elif choice == 3:
            name = Prompt.ask(t("pf_pick"), console=self.c).strip()
            self.svc.remove_profile(name, dry_run=self.dry_run)
            if self.dry_run:
                self._dry_note("dry_would_profile_remove", name=name)
            else:
                self.say(t("pf_removed", name=name))

    def uninstall(self) -> None:
        self.say(t("un_info"))
        if not self.dry_run and not Confirm.ask(t("un_confirm"), default=False, console=self.c):
            self.say(t("cancelled"))
            return
        delete = False
        if not self.dry_run:
            delete = Confirm.ask(t("un_secret"), default=False, console=self.c)
        res = self.svc.uninstall(True, delete_secret=delete)
        if res.changed:
            self.show_diff(res.diff)
        else:
            self.say(t("no_changes"))
        self.show_notes(res)
        if self.dry_run:
            self.say(t("dry_run_done"), "yellow")
            return
        if not Confirm.ask(t("apply_confirm"), default=True, console=self.c):
            self.say(t("cancelled"))
            return
        res = self.svc.uninstall(False, delete_secret=delete)
        self.show_notes(res)
        self.say(t("un_done"), "green")

    def launch(self) -> None:
        target = Prompt.ask(t("ln_target"), choices=["cli", "app"], default="cli", console=self.c)
        args: list[str] = []
        if target == "app":
            self.say(t("ln_app_experimental"), "yellow")
        else:
            args = Prompt.ask(t("ln_args"), default="", console=self.c).split()
        if self.dry_run:
            self.say(t("dry_run_done"), "yellow")
            return
        code = self.svc.launch(target, args)
        self.say(t("ln_started", code=code) if target == "cli" else t("ln_app_started"))


def run(svc: SetupService | None = None, *, dry_run: bool = False, console: Console | None = None) -> int:
    app = TuiApp(svc or SetupService(), console or _make_console(), dry_run)
    try:
        return app.loop()
    except (KeyboardInterrupt, EOFError):
        app.say(t("bye"))
        return 130
