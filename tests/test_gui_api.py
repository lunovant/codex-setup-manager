from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_setup import app as app_mod
from codex_setup.app import SetupService
from codex_setup.core import paths
from codex_setup.diagnostics.api_test import ApiTestReport, Outcome, Problem, StepResult
from codex_setup.gui.api import GuiApi
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.secrets import SecretStore

KEY = "sk-test-SECRET-1234567890"


def _make(system: str = "macos") -> GuiApi:
    svc = SetupService(secret_store=SecretStore(backend="session"))
    svc._platform = PlatformInfo(system, "25", "arm64")  # type: ignore[arg-type]
    svc._install = CodexInstall(None, None, False, False, None, None, "n/a")
    return GuiApi(svc, lang="en")


@pytest.fixture
def gui() -> GuiApi:
    return _make()


def _cfg() -> Path:
    return paths.config_path()


def test_status_defaults(gui):
    res = gui.status()
    assert res["ok"] and res["config"]["state"] == "missing"
    assert res["default_base_url"] == "https://api.lunovant.tech/v1"
    json.dumps(res)


def test_preview_does_not_write_and_apply_does(gui):
    prev = gui.preview_setup(None, "gpt-6.1-sol")
    assert prev["ok"] and prev["changed"] and "lunovant" in prev["diff"].lower()
    assert not _cfg().exists()
    res = gui.quick_setup(None, "gpt-6.1-sol", KEY, "session", dry_run=True)
    assert res["ok"] and not _cfg().exists()
    res = gui.quick_setup(None, "gpt-6.1-sol", KEY, "session")
    assert res["ok"] and res["backend"] == "session"
    text = _cfg().read_text(encoding="utf-8")
    assert 'model = "gpt-6.1-sol"' in text and "api.lunovant.tech" in text
    assert KEY not in text


def test_key_never_in_any_result(gui):
    results = [
        gui.quick_setup(None, "gpt-6.1-sol", KEY, "session"),
        gui.status(),
        gui.models(),
        gui.set_api(None, KEY + "2", False, False),
        gui.set_api("https://example.com/v1", KEY + "3", False, True),
        gui.change_model("gpt-6-sol", True),
        gui.backups(),
        gui.diagnose(None),
        gui.diagnose(f"error {KEY} Couldn't check Windows setup"),
        gui.uninstall(False, True),
        gui.launch("cli"),
        gui.quick_setup("not a url", "m", KEY, "session"),
        gui.quick_setup(None, "gpt-6.1-sol", KEY, "bogus"),
    ]
    for r in results:
        blob = json.dumps(r)
        assert KEY not in blob
    assert gui.status()["masked_key"] != KEY


def test_errors_are_redacted(gui, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError(f"upstream said {KEY} is bad")

    monkeypatch.setattr(gui._svc, "quick_setup", boom)
    res = gui.quick_setup(None, "gpt-6.1-sol", KEY, "session")
    assert res["ok"] is False and KEY not in res["error"] and "RuntimeError" in res["error"]


def test_validation_error_is_json(gui):
    res = gui.quick_setup(None, "bad model name!", KEY, "session")
    assert res["ok"] is False and res["error"]


def test_change_model_and_models(gui):
    gui.quick_setup(None, "gpt-6.1-sol", KEY, "session")
    assert gui.change_model("gpt-6-luna", True)["changed"]
    assert "gpt-6-luna" not in _cfg().read_text(encoding="utf-8").split("model_provider")[0]
    assert gui.change_model("gpt-6-luna", False)["ok"]
    assert gui.status()["model"] == "gpt-6-luna"
    assert "gpt-6.1-sol" in gui.models()["models"]


def test_sandbox_options_non_windows(gui, monkeypatch):
    res = gui.sandbox_options()
    assert res["ok"] and res["applicable"] is False and res["modes"] == []
    assert gui.set_sandbox("unelevated", True)["ok"] is False
    assert gui.set_sandbox("disabled", True)["ok"] is False


def test_sandbox_windows_modes():
    gui = _make("windows")
    res = gui.sandbox_options()
    assert res["applicable"] and res["recommended"] == "unelevated"
    assert "off" not in " ".join(res["modes"]) and "disabled" not in res["modes"]
    assert gui.set_sandbox("unelevated", True)["ok"]
    assert gui.set_sandbox("danger-full-access", True)["ok"] is False


def test_test_connection_monkeypatched(gui, monkeypatch):
    gui.quick_setup(None, "gpt-6.1-sol", KEY, "session")
    report = ApiTestReport(
        [
            StepResult("connect", Outcome.OK, None, "ok", 200, "at_connect_ok", {"http": "200"}),
            StepResult("responses", Outcome.FAIL, Problem.UNAUTHORIZED, "401", 401, "at_unauthorized"),
        ],
        Outcome.FAIL,
    )
    seen = {}

    def fake(base_url, key, model):
        seen.update(base_url=base_url, key=key, model=model)
        return report

    monkeypatch.setattr(app_mod, "run_api_test", fake)
    res = gui.test_connection(None)
    assert res["ok"] and res["overall"] == "fail" and res["success"] is False
    assert [s["outcome"] for s in res["steps"]] == ["ok", "fail"]
    assert "401" in res["steps"][1]["problem_text"] and res["steps"][0]["detail_text"]
    assert seen["key"] == KEY and KEY not in json.dumps(res)


def test_test_connection_without_key_is_error(gui):
    assert gui.test_connection(None)["ok"] is False


def test_backups_roundtrip(gui):
    gui.quick_setup(None, "gpt-6.1-sol", KEY, "session")
    created = gui.create_backup()
    assert created["ok"] and created["path"]
    items = gui.backups()["backups"]
    assert items
    gui.change_model("gpt-6-luna", False)
    prev = gui.restore_backup(items[0]["id"], True)
    assert prev["ok"] and 'gpt-6-luna' in _cfg().read_text(encoding="utf-8")
    assert gui.restore_backup(items[0]["id"], False)["ok"]
    assert gui.status()["model"] == "gpt-6.1-sol"


def test_diagnose_text_translated(gui):
    res = gui.diagnose("Couldn't check Windows setup")
    assert res["ok"] and res["issues"] and res["issues"][0]["steps"]
    assert gui.diagnose(None)["checks"]


def test_env_install_needs_consent(gui):
    assert gui.env_install(False)["ok"] is False


def test_uninstall_preview(gui):
    gui.quick_setup(None, "gpt-6.1-sol", KEY, "session")
    before = _cfg().read_text(encoding="utf-8")
    assert gui.uninstall(False, True)["ok"]
    assert _cfg().read_text(encoding="utf-8") == before


def test_strings_same_keys():
    gui = _make()
    en, vi = gui.strings("en"), gui.strings("vi")
    assert en["ok"] and vi["ok"]
    assert set(en["strings"]) == set(vi["strings"])
    assert en["strings"]["g_nav_quick"] != vi["strings"]["g_nav_quick"]
    assert gui.strings("xx")["lang"] == "en"
    json.dumps(en)


def test_packaged_web_files():
    from codex_setup.gui.app import index_path, web_dir

    assert index_path().is_file()
    for name in ("index.html", "app.js", "style.css"):
        text = (web_dir() / name).read_text(encoding="utf-8")
        stripped = text.replace("https://api.lunovant.tech/v1", "")
        assert "http://" not in stripped and "https://" not in stripped, name


def test_csp_allows_pywebview_bridge():
    """pywebview injects its JS bridge with eval; a CSP without 'unsafe-eval' leaves the UI blank."""
    import re

    from codex_setup.gui.app import index_path

    html = index_path().read_text(encoding="utf-8")
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]*)"', html)
    if csp:
        script_src = re.search(r"script-src([^;]*)", csp.group(1))
        assert script_src and "'unsafe-eval'" in script_src.group(1)
