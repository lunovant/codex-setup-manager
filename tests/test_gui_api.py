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
    assert en["strings"]["g_nav_oneclick"] != vi["strings"]["g_nav_oneclick"]
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


# -- one-click GUI API ----------------------------------------------------------------
import threading as _th
import time as _time

from codex_setup.app import OneClickResult as _OCR


def _wait_done(gui: GuiApi, timeout: float = 5.0) -> dict:
    end = _time.time() + timeout
    while _time.time() < end:
        res = gui.one_click_poll()
        if not res["running"]:
            return res
        _time.sleep(0.02)
    raise AssertionError("one-click run did not finish")


def test_one_click_start_poll_no_key_leak(gui, monkeypatch):
    def fake(key, base_url=None, progress=None, **kw):
        progress("check_key", {})
        progress("check_key", {"valid": True, "plan": "P", "note": f"echo {key}"})
        progress("fetch_models", {"models": ["gpt-6"]})
        progress("probe:gpt-6", {"model": "gpt-6", "ok": True, "latency_ms": 1200})
        progress("done", {"ok": True, "code": "ok"})
        return _OCR(True, "ok", f"done {key}", {"valid": True}, [{"model": "gpt-6", "ok": True}],
                    "gpt-6", None, None)

    monkeypatch.setattr(gui._svc, "one_click_setup", fake)
    assert gui.one_click_start(KEY)["ok"]
    res = _wait_done(gui)
    assert [s["step"] for s in res["steps"]][-1] == "done"
    assert res["result"]["ok"] and res["result"]["default_model"] == "gpt-6"
    assert KEY not in json.dumps(res)


def test_one_click_only_one_run(gui, monkeypatch):
    gate = _th.Event()

    def slow(key, base_url=None, progress=None, **kw):
        gate.wait(5)
        return _OCR(False, "key_invalid", "x")

    monkeypatch.setattr(gui._svc, "one_click_setup", slow)
    assert gui.one_click_start("a")["ok"]
    second = gui.one_click_start("b")
    assert not second["ok"] and second["busy"]
    assert gui.one_click_poll()["running"]
    gate.set()
    assert _wait_done(gui)["result"]["code"] == "key_invalid"
    assert gui.one_click_start("c")["ok"]
    _wait_done(gui)


def test_one_click_exception_is_json(gui, monkeypatch):
    def boom(key, base_url=None, progress=None, **kw):
        raise RuntimeError(f"bad {key}")

    monkeypatch.setattr(gui._svc, "one_click_setup", boom)
    gui.one_click_start(KEY)
    res = _wait_done(gui)
    assert res["result"]["ok"] is False and KEY not in json.dumps(res)


_BEARER_CFG = (
    'model_provider = "lunovant"\nmodel = "gpt-6"\n\n[model_providers.lunovant]\n'
    'name = "Lunovant"\nbase_url = "https://api.lunovant.tech/v1"\nwire_api = "responses"\n'
    f'experimental_bearer_token = "{KEY}"\n'
)


def test_reprobe_model_updates_state(gui, monkeypatch):
    from codex_setup.core.state import AppState, load_state, save_state
    from codex_setup.diagnostics import model_probe

    _cfg().parent.mkdir(parents=True, exist_ok=True)
    _cfg().write_text(_BEARER_CFG, encoding="utf-8")
    st = AppState()
    st.one_click = {"base_url": "https://api.lunovant.tech/v1", "results": [
        {"model": "gpt-6", "ok": False, "error": "429"}, {"model": "gpt-7", "ok": True}]}
    save_state(st, gui._svc._env)
    seen = {}

    def fake(url, key, models, **kw):
        seen.update(url=url, key=key, models=models)
        return [{"model": models[0], "ok": True, "latency_ms": 5, "error": None}]

    monkeypatch.setattr(model_probe, "probe_models", fake)
    res = gui.reprobe_model("gpt-6")
    assert res["ok"] and res["result"]["ok"]
    assert seen == {"url": "https://api.lunovant.tech/v1", "key": KEY, "models": ["gpt-6"]}
    saved = load_state(gui._svc._env).one_click["results"]
    assert [r["ok"] for r in saved] == [True, True]
    assert KEY not in json.dumps(res)
    last = gui.one_click_last()
    assert last["has_last"] and KEY not in json.dumps(last)


def test_launch_windows_bearer_only(monkeypatch):
    import subprocess as sp

    gui = _make("windows")
    gui._svc._install = CodexInstall("C:/codex.exe", "1", True, False, None, None, "n/a")
    _cfg().parent.mkdir(parents=True, exist_ok=True)
    _cfg().write_text(_BEARER_CFG, encoding="utf-8")
    calls = []
    monkeypatch.setattr(sp, "Popen", lambda *a, **k: calls.append((a, k)))
    res = gui.launch("cli")
    assert res["ok"], res
    assert calls and calls[0][0][0] == ["C:/codex.exe"]
    assert KEY not in json.dumps(res)


def test_open_url_whitelist(gui):
    assert not gui.open_url("https://evil.example")["ok"]


def test_reprobe_stale_state_never_sends_key_to_old_endpoint(gui, monkeypatch):
    from codex_setup.core.state import AppState, save_state
    from codex_setup.diagnostics import model_probe

    _cfg().parent.mkdir(parents=True, exist_ok=True)
    _cfg().write_text(_BEARER_CFG, encoding="utf-8")
    st = AppState()
    st.one_click = {"base_url": "https://old.example/v1", "results": [{"model": "gpt-6", "ok": True}]}
    save_state(st, gui._svc._env)
    calls = []
    monkeypatch.setattr(model_probe, "probe_models", lambda *a, **k: calls.append(a) or [])
    assert gui.one_click_last()["has_last"] is False
    res = gui.reprobe_model("gpt-6")
    assert not res["ok"] and calls == []


def test_reprobe_failed_run_uses_run_context_and_persists_nothing(gui, monkeypatch):
    from codex_setup.core.state import load_state
    from codex_setup.diagnostics import model_probe

    monkeypatch.setattr(gui._svc, "one_click_setup",
                        lambda key, base_url=None, progress=None, **kw: _OCR(False, "no_model_works", "x"))
    seen = {}

    def fake(url, key, models, **kw):
        seen.update(url=url, key=key)
        return [{"model": models[0], "ok": True, "latency_ms": 1, "error": None}]

    monkeypatch.setattr(model_probe, "probe_models", fake)
    gui.one_click_start(KEY)
    _wait_done(gui)
    res = gui.reprobe_model("gpt-6")  # fresh machine: no config at all
    assert res["ok"] and seen["key"] == KEY and seen["url"] == "https://api.lunovant.tech/v1"
    assert load_state(gui._svc._env).one_click is None
    assert KEY not in json.dumps(res)


def test_one_click_holds_shared_lock(gui, monkeypatch):
    gate, entered = _th.Event(), _th.Event()

    def slow(key, base_url=None, progress=None, **kw):
        entered.set()
        gate.wait(5)
        return _OCR(False, "key_invalid", "x")

    monkeypatch.setattr(gui._svc, "one_click_setup", slow)
    gui.one_click_start("a")
    assert entered.wait(5)
    done = _th.Event()
    _th.Thread(target=lambda: (gui.backups(), done.set()), daemon=True).start()
    assert not done.wait(0.3)  # config-touching APIs wait for the worker's lock
    gate.set()
    assert done.wait(5)
    _wait_done(gui)


# -- detect_lines: which lines a key covers (GET /models only) -----------------------------------
import httpx as _httpx


def _models_client(ids=None, status=200):
    seen: list[str] = []

    def handler(req: _httpx.Request) -> _httpx.Response:
        seen.append(req.url.path)
        if status != 200:
            return _httpx.Response(status)
        return _httpx.Response(200, json={"data": [{"id": i} for i in (ids or [])]})

    c = _httpx.Client(transport=_httpx.MockTransport(handler))
    c.seen = seen  # type: ignore[attr-defined]
    return c


@pytest.mark.parametrize(
    "ids,lines",
    [
        (["gpt-6.1-sol", "gpt-6-luna"], ["codex"]),
        (["claude-sonnet-4"], ["claude"]),
        (["gpt-6.1-sol", "claude-sonnet-4", "gemini-x"], ["codex", "claude"]),
    ],
)
def test_detect_lines(gui, ids, lines):
    c = _models_client(ids)
    out = gui.detect_lines(KEY, client=c)
    assert out == {"ok": True, "lines": lines}
    assert c.seen == ["/v1/models"]  # no usage call, no probes
    assert KEY not in repr(out)
    assert not _cfg().exists()
    assert KEY not in json.dumps(gui._svc.status().last_test or {})


def test_detect_lines_errors(gui):
    assert gui.detect_lines(KEY, client=_models_client([]))["error_code"] == "not_codex_key"
    assert gui.detect_lines(KEY, client=_models_client(status=401))["error_code"] == "key_invalid"
    assert gui.detect_lines(KEY, client=_models_client(status=500))["error_code"] == "network"
    assert gui.detect_lines("  ")["error_code"] == "key_empty"
    for out in (gui.detect_lines(KEY, client=_models_client([])),):
        assert out["ok"] is False and KEY not in repr(out)


def test_detect_lines_saves_nothing(gui):
    gui.detect_lines(KEY, client=_models_client(["gpt-6.1-sol"]))
    st_file = paths.state_path() if hasattr(paths, "state_path") else None
    assert st_file is None or not st_file.exists()
    assert gui._svc.get_key("LUNOVANT_API_KEY") is None


def _web(name: str) -> str:
    from codex_setup.gui.app import web_dir

    return (web_dir() / name).read_text(encoding="utf-8")


def test_removed_tabs_are_gone_from_html():
    html = _web("index.html")
    assert 'data-tab="quick"' not in html and 'data-tab="api"' not in html
    for tab in ("model", "test", "sandbox", "backup", "diag", "launch", "uninstall"):
        assert f'data-tab="{tab}"' in html


def test_every_js_element_id_exists_in_html():
    import re

    html, js = _web("index.html"), _web("app.js")
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    used = set(re.findall(r'\$\("([^"]+)"\)', js))
    assert used - ids == set()
    # ids the JS creates itself are not looked up with $(), so nothing else is allowed to be missing
    assert not any(i.startswith(("q-", "a-")) for i in used)


def test_gui_string_keys_used_by_web_exist():
    import re

    from codex_setup.gui import strings

    assert set(strings.EN) == set(strings.VI)
    gui = _make()
    table = gui.strings("en")["strings"]
    keys = set(re.findall(r'data-i18n="([^"]+)"', _web("index.html")))
    keys |= set(re.findall(r'\bt\("([a-z0-9_]+)"', _web("app.js")))
    assert {k for k in keys if k not in table} == set()
