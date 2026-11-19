"""v0.4.0: Claude Code line (detection, probe, settings.json ownership, modes, GUI/CLI)."""

from __future__ import annotations

import io
import json
import os
import shlex
import stat
import time

import httpx
import pytest

from codex_setup import main as cli
from codex_setup.app import SetupService
from codex_setup.core import claude_config, paths
from codex_setup.core.state import load_state
from codex_setup.diagnostics import model_probe
from codex_setup.gui.api import GuiApi
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security import launcher
from codex_setup.security.secrets import SecretStore

KEY = "sk-lunovant-SECRET-1234567890"
USAGE_OK = {"isValid": True, "status": "active", "expires_at": "2099-01-01T00:00:00Z",
            "days_until_expiry": 900, "remaining": 12.5, "planName": "Pro"}
GPT = ["gpt-6.1-sol", "gpt-6-luna"]
CLAUDE = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-4-1-20250805",
          "claude-sonnet-4-5"]


def make_client(models, *, fail=()):
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        p = req.url.path
        assert req.headers["authorization"] == f"Bearer {KEY}"
        if p == "/v1/usage":
            return httpx.Response(200, json=USAGE_OK)
        if p == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        if p == "/v1/responses":
            return httpx.Response(200, json={"object": "response", "output": []})
        if p == "/v1/messages":
            assert req.headers["x-api-key"] == KEY
            assert req.headers["anthropic-version"] == "2023-06-01"
            if json.loads(req.content)["model"] in fail:
                return httpx.Response(429, text="slow down")
            return httpx.Response(200, json={"type": "message", "content": []})
        return httpx.Response(404)

    c = httpx.Client(transport=httpx.MockTransport(handler))
    c.seen = seen  # type: ignore[attr-defined]
    return c


@pytest.fixture
def svc() -> SetupService:
    s = SetupService(secret_store=SecretStore(backend="session"))
    s._platform = PlatformInfo("macos", "25", "arm64")
    s._install = CodexInstall(None, None, False, False, None, None, "n/a")
    return s


def _settings():
    return paths.claude_settings_path()


def _profile():
    return paths.claude_profile_path()


def _write_settings(text: str):
    _settings().parent.mkdir(parents=True, exist_ok=True)
    _settings().write_bytes(text.encode("utf-8"))


def _env_of(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")).get("env", {})


# -- line detection ----------------------------------------------------------------
def test_detect_codex_only(svc):
    res = svc.one_click_setup(KEY, client=make_client(GPT))
    assert res.ok and list(res.sections) == ["codex"] and res.line == "codex"
    assert not _settings().exists() and not _profile().exists()


def test_detect_claude_only(svc):
    c = make_client(CLAUDE)
    res = svc.one_click_setup(KEY, client=c)
    assert res.ok and list(res.sections) == ["claude"] and res.line == "claude"
    assert not paths.config_path().exists()
    assert not any(r.url.path == "/v1/responses" for r in c.seen)
    assert res.default_model == "claude-opus-5-5"


def test_detect_both(svc):
    res = svc.one_click_setup(KEY, client=make_client(GPT + CLAUDE))
    assert res.ok and set(res.sections) == {"codex", "claude"}
    assert paths.config_path().exists() and _settings().exists()
    # Codex never probes claude models
    state = load_state()
    assert not any(m.startswith("claude-") for m in state.one_click["models"])


def test_codex_only_probes_gpt_models(svc):
    c = make_client(GPT + CLAUDE + ["gemini-2.5-pro", "deepseek-v4-pro"])
    res = svc.one_click_setup(KEY, client=c)
    probed = {json.loads(r.content)["model"] for r in c.seen if r.url.path == "/v1/responses"}
    assert res.ok and probed == set(GPT)
    assert [m["model"] for m in res.sections["codex"].models] == GPT


def test_claude_failure_does_not_block_codex(svc):
    res = svc.one_click_setup(KEY, client=make_client(GPT + CLAUDE, fail=set(CLAUDE)))
    assert not res.ok and res.sections["codex"].ok and not res.sections["claude"].ok
    assert res.sections["claude"].code == "no_model_works"
    assert not _settings().exists() and paths.config_path().exists()


# -- probe -------------------------------------------------------------------------
def test_probe_request_shape_and_only_three_models(svc):
    c = make_client(CLAUDE)
    res = svc.one_click_setup(KEY, client=c)
    posts = [r for r in c.seen if r.url.path == "/v1/messages"]
    assert sorted(json.loads(r.content)["model"] for r in posts) == sorted(
        ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"])
    r = posts[0]
    assert r.method == "POST" and str(r.url) == "https://api.lunovant.tech/v1/messages"
    assert r.headers["x-api-key"] == KEY and r.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(r.content)["max_tokens"] == 8
    assert json.loads(r.content)["messages"] == [{"role": "user", "content": "Reply with OK"}]
    rows = {m["model"]: m for m in res.models}
    assert rows["claude-opus-4-1-20250805"]["tested"] is False
    assert rows["claude-opus-5-5"]["ok"] is True and rows["claude-opus-5-5"]["role"] == "opus"


def test_pick_models_fallback_to_newest():
    avail = ["claude-opus-4-1-20250805", "claude-opus-4-5", "claude-sonnet-4-5", "claude-3-5-haiku-20241022"]
    picks = claude_config.pick_models(avail)
    assert picks == {"opus": "claude-opus-4-5", "sonnet": "claude-sonnet-4-5",
                     "haiku": "claude-3-5-haiku-20241022"}
    only = claude_config.pick_models(["claude-sonnet-4-5"])
    assert set(only.values()) == {"claude-sonnet-4-5"}
    assert claude_config.pick_models(["gpt-6"]) == {}


def test_failed_family_uses_default_model(svc):
    res = svc.one_click_setup(KEY, client=make_client(CLAUDE, fail={"claude-haiku-5-5"}))
    assert res.ok
    env = _env_of(_settings())
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "claude-opus-5-5"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet-5-5"


# -- settings.json -----------------------------------------------------------------
ORIGINAL = json.dumps({"theme": "dark", "permissions": {"allow": ["Bash(ls)"]},
                       "env": {"FOO": "1"}}, indent=2) + "\n"


def test_settings_write_keeps_foreign_keys_mode_backup_ownership(svc):
    _write_settings(ORIGINAL)
    res = svc.one_click_setup(KEY, client=make_client(CLAUDE))
    assert res.ok and res.backup_path is not None and res.backup_path.is_file()
    data = json.loads(_settings().read_text())
    assert data["theme"] == "dark" and data["permissions"] == {"allow": ["Bash(ls)"]}
    env = data["env"]
    assert env["FOO"] == "1"
    assert env["ANTHROPIC_BASE_URL"] == "https://api.lunovant.tech"  # origin, no /v1
    assert env["ANTHROPIC_AUTH_TOKEN"] == KEY
    assert env["ANTHROPIC_MODEL"] == env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-opus-5-5"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet-5-5"
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "claude-haiku-5-5"
    if os.name == "posix":
        assert stat.S_IMODE(_settings().stat().st_mode) == 0o600
        assert stat.S_IMODE(_profile().stat().st_mode) == 0o600
    rec = load_state().claude
    assert rec["settings_path"] == str(_settings())
    assert set(rec["written"]) == set(claude_config.env_values("u", "k", claude_config.PREFERRED))
    state_text = json.dumps(rec)
    assert KEY not in state_text
    assert not (paths.app_state_dir() / "state.json").read_text().count(KEY)
    # claude backups never show up in the config.toml backup list
    assert svc.backup_list() == []


def test_settings_invalid_json_is_not_overwritten(svc):
    _write_settings("{ not json")
    res = None
    with pytest.raises(Exception):
        res = svc.one_click_setup(KEY, client=make_client(CLAUDE))
    assert res is None and _settings().read_text() == "{ not json"


def test_profile_file_only_env(svc):
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    data = json.loads(_profile().read_text())
    assert list(data) == ["env"]
    assert data["env"] == _env_of(_settings())
    assert svc.claude_launch_command("personal") == f"claude --settings {shlex.quote(str(_profile()))}"
    assert svc.claude_launch_command("lunovant") == "claude"


def test_respects_claude_config_dir(svc, tmp_path):
    assert paths.claude_settings_path() == tmp_path / "claude_home" / "settings.json"
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    assert (tmp_path / "claude_home" / "settings.json").is_file()
    assert (tmp_path / "claude_home" / "lunovant-settings.json").is_file()
    assert not (tmp_path / "home" / ".claude").exists()


# -- personal login detection ----------------------------------------------------------
def test_personal_login_detection(svc, tmp_path):
    state = paths.claude_global_state_path()
    assert state == tmp_path / "claude_home" / ".claude.json"
    assert svc.claude_login_present() is False
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"userID": "x", "primaryApiKey": "sk-secret"}))
    assert svc.claude_login_present() is False
    state.write_text(json.dumps({"oauthAccount": {}}))
    assert svc.claude_login_present() is False
    state.write_text(json.dumps({"oauthAccount": {"emailAddress": "a@b.c"}}))
    assert svc.claude_login_present() is True
    state.write_text("not json")
    assert svc.claude_login_present() is False


def test_login_detection_default_location(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    path = paths.claude_global_state_path()
    assert path == tmp_path / "home" / ".claude.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"oauthAccount": {"uuid": "1"}}))
    assert claude_config.personal_login_present() is True
    assert paths.claude_settings_path() == tmp_path / "home" / ".claude" / "settings.json"


def test_never_touches_credentials(svc, tmp_path):
    home = tmp_path / "claude_home"
    home.mkdir(parents=True)
    (home / ".credentials.json").write_text('{"claudeAiOauth": "x"}')
    (home / ".claude.json").write_text(json.dumps({"oauthAccount": {"a": 1}}))
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in home.iterdir()}
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    svc.claude_set_mode("personal")
    svc.uninstall()
    for name, (data, mtime) in before.items():
        p = home / name
        assert p.read_bytes() == data and p.stat().st_mtime_ns == mtime


# -- modes ------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    ORIGINAL,
    '{"theme":"dark",\n    "env": {"FOO": "1"}}',  # odd formatting, no trailing newline
    "﻿" + ORIGINAL,
])
def test_mode_round_trip_restores_original_exactly(svc, text):
    _write_settings(text)
    raw = _settings().read_bytes()
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    assert svc.claude_current_mode() == "lunovant"
    assert _settings().read_bytes() != raw
    svc.claude_set_mode("personal")
    assert _settings().read_bytes() == raw
    assert svc.claude_current_mode() == "personal"
    assert _profile().exists()  # `claude --settings ...` keeps working
    svc.claude_set_mode("lunovant")
    assert svc.claude_current_mode() == "lunovant"
    assert _env_of(_settings())["ANTHROPIC_AUTH_TOKEN"] == KEY
    svc.claude_set_mode("personal")
    assert _settings().read_bytes() == raw


def test_mode_round_trip_when_no_settings_file(svc):
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    svc.claude_set_mode("personal")
    assert not _settings().exists()
    svc.claude_set_mode("lunovant")
    assert svc.claude_current_mode() == "lunovant"


def test_personal_at_setup_leaves_settings_alone(svc):
    _write_settings(ORIGINAL)
    raw = _settings().read_bytes()
    res = svc.one_click_setup(KEY, client=make_client(CLAUDE), mode="personal")
    assert res.ok and res.mode == "personal"
    assert _settings().read_bytes() == raw and _profile().exists()
    assert svc.claude_installed() and svc.claude_current_mode() == "personal"
    assert "--settings" in res.message
    svc.claude_set_mode("lunovant")
    assert svc.claude_current_mode() == "lunovant"


def test_displaced_user_values_are_restored(svc):
    _write_settings(json.dumps({"env": {"ANTHROPIC_MODEL": "my-model", "FOO": "1"}}, indent=2) + "\n")
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    assert _env_of(_settings())["ANTHROPIC_MODEL"] == "claude-opus-5-5"
    svc.claude_set_mode("personal")
    assert _env_of(_settings()) == {"ANTHROPIC_MODEL": "my-model", "FOO": "1"}


def test_set_mode_requires_setup(svc):
    with pytest.raises(Exception):
        svc.claude_set_mode("lunovant")


def test_dry_run_diff_masks_token(svc):
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    svc.claude_set_mode("personal")
    res = svc.claude_set_mode("lunovant", dry_run=True)
    assert res.changed and res.dry_run and KEY not in res.diff and "****" in res.diff
    assert svc.claude_current_mode() == "personal"  # nothing written


# -- uninstall -------------------------------------------------------------------------
def test_uninstall_removes_only_our_unchanged_values(svc):
    _write_settings(ORIGINAL)
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    data = json.loads(_settings().read_text())
    data["env"]["ANTHROPIC_MODEL"] = "user-edited"
    data["extra"] = True
    _settings().write_text(json.dumps(data, indent=2))
    res = svc.uninstall()
    assert res.changed
    out = json.loads(_settings().read_text())
    assert out["env"] == {"FOO": "1", "ANTHROPIC_MODEL": "user-edited"}
    assert out["theme"] == "dark" and out["extra"] is True
    assert not _profile().exists()
    assert load_state().claude is None
    assert any(k == "un_claude_field_changed" for k, _ in res.notes)
    assert KEY not in res.diff


def test_uninstall_restores_original_exactly(svc):
    _write_settings(ORIGINAL)
    raw = _settings().read_bytes()
    svc.one_click_setup(KEY, client=make_client(GPT + CLAUDE))
    svc.uninstall()
    assert _settings().read_bytes() == raw
    assert not _profile().exists()
    assert load_state().claude is None


def test_uninstall_without_original_file_removes_it(svc):
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    svc.uninstall()
    assert not _settings().exists() and not _profile().exists()


def test_uninstall_when_nothing_installed(svc):
    res = svc.uninstall()
    assert not res.changed


# -- GUI api -----------------------------------------------------------------------------
def _gui(svc, models):
    client = make_client(models)
    orig = svc.one_click_setup
    svc.one_click_setup = lambda key, base_url=None, progress=None, **kw: orig(  # type: ignore[method-assign]
        key, base_url, progress, client=client, **kw)
    return GuiApi(svc, lang="en")


def _wait(gui):
    for _ in range(200):
        res = gui.one_click_poll()
        if not res["running"]:
            return res
        time.sleep(0.02)
    raise AssertionError("did not finish")


def test_gui_returns_both_sections(svc):
    gui = _gui(svc, GPT + CLAUDE)
    assert gui.one_click_start(KEY)["ok"]
    res = _wait(gui)
    secs = res["result"]["sections"]
    assert set(secs) == {"codex", "claude"} and secs["claude"]["ok"] and secs["codex"]["ok"]
    assert secs["claude"]["line"] == "claude"
    assert secs["claude"]["claude_models"]["opus"] == "claude-opus-5-5"
    assert any(m["model"] == "claude-sonnet-4-5" and m["tested"] is False
               for m in secs["claude"]["models"])
    steps = [s["step"] for s in res["steps"]]
    assert "claude_models" in steps and "claude_write" in steps and steps[-1] == "done"
    st = gui.status()
    assert st["claude"]["installed"] and st["claude"]["mode"] == "lunovant"
    assert st["claude"]["command"] == "claude" and st["claude"]["terminal"] is True
    last = gui.one_click_last()
    assert last["has_last"] and set(last["sections"]) == {"codex", "claude"}
    for blob in (res, st, last, gui.status()):
        assert KEY not in json.dumps(blob)
    assert KEY not in (paths.app_state_dir() / "state.json").read_text()


def test_gui_claude_only_and_mode(svc):
    gui = _gui(svc, CLAUDE)
    gui.one_click_start(KEY)
    res = _wait(gui)
    assert res["result"]["ok"] and list(res["result"]["sections"]) == ["claude"]
    assert res["result"]["line"] == "claude"
    out = gui.set_mode("personal", False, "claude")
    assert not out["ok"]  # no personal Claude login on this machine
    state = paths.claude_global_state_path()
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"oauthAccount": {"x": 1}}))
    assert gui.status()["claude"]["login"] is True
    out = gui.set_mode("personal", False, "claude")
    assert out["ok"] and out["mode"] == "personal"
    assert KEY not in json.dumps(out)
    assert gui.status()["claude"]["command"].startswith("claude --settings")
    out = gui.set_mode("lunovant", False, "claude")
    assert out["ok"] and out["mode"] == "lunovant" and KEY not in json.dumps(out)
    assert not gui.set_mode("lunovant", False, "nope")["ok"]


def test_gui_personal_choice_ignored_without_login(svc):
    gui = _gui(svc, CLAUDE)
    gui.one_click_start(KEY, "personal", "personal")
    res = _wait(gui)
    assert res["result"]["sections"]["claude"]["mode"] == "lunovant"
    assert svc.claude_current_mode() == "lunovant"


def test_gui_reprobe_claude(svc, monkeypatch):
    gui = _gui(svc, CLAUDE)
    gui.one_click_start(KEY)
    _wait(gui)
    seen = {}

    def fake(url, key, models, **kw):
        seen.update(url=url, key=key, models=models)
        return [{"model": models[0], "ok": True, "latency_ms": 5, "error": None, "tested": True}]

    monkeypatch.setattr(model_probe, "probe_claude_models", fake)
    out = gui.reprobe_model("claude-haiku-5-5", "claude")
    assert out["ok"] and out["result"]["ok"] and KEY not in json.dumps(out)
    assert seen["url"] == "https://api.lunovant.tech" and seen["key"] == KEY
    rows = load_state().claude["one_click"]["results"]
    assert next(r for r in rows if r["model"] == "claude-haiku-5-5")["role"] == "haiku"


def test_gui_launch_claude(svc, monkeypatch):
    gui = _gui(svc, CLAUDE)
    gui.one_click_start(KEY)
    _wait(gui)
    calls = []
    monkeypatch.setattr("codex_setup.gui.api.shutil.which", lambda n: "/usr/bin/claude")
    monkeypatch.setattr(launcher, "open_terminal", lambda system, argv, **kw: calls.append((system, argv)))
    assert gui.launch("claude")["ok"]
    assert calls == [("macos", ["claude"])]
    svc.claude_set_mode("personal")
    gui.launch("claude")
    assert calls[-1][1][:2] == ["claude", "--settings"] and calls[-1][1][2] == str(_profile())
    # macOS: a GUI PATH without claude must not block the Terminal launch
    monkeypatch.setattr("codex_setup.gui.api.shutil.which", lambda n: None)
    assert gui.launch("claude")["ok"]
    svc._platform = PlatformInfo("linux", "6", "x86_64")
    assert not gui.launch("claude")["ok"]


# -- launcher ----------------------------------------------------------------------------------
def test_open_terminal_macos_quotes():
    calls = []
    launcher.open_terminal("macos", ["claude", "--settings", "/a b/x.json"],
                           popen=lambda argv, **kw: calls.append(argv))
    argv = calls[0]
    assert argv[0] == "osascript" and "do script" in argv[-1] and "'/a b/x.json'" in argv[-1]


def test_open_terminal_linux_and_support():
    calls = []
    which = lambda n: "/usr/bin/xterm" if n == "xterm" else None  # noqa: E731
    assert launcher.terminal_supported("linux", which=which)
    launcher.open_terminal("linux", ["claude"], popen=lambda argv, **kw: calls.append(argv), which=which)
    assert calls == [["xterm", "-e", "claude"]]
    assert not launcher.terminal_supported("linux", which=lambda n: None)
    with pytest.raises(Exception):
        launcher.open_terminal("linux", ["claude"], popen=lambda *a, **k: None, which=lambda n: None)


# -- CLI ---------------------------------------------------------------------------------------
def _stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_cli_summary_for_claude_key(svc, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    cli._SEEN_SECRETS.clear()
    real = svc.one_click_setup
    client = make_client(CLAUDE)
    monkeypatch.setattr(svc, "one_click_setup",
                        lambda *a, **kw: real(*a, client=client, **kw))
    _stdin(monkeypatch, KEY + "\n")
    assert cli.main(["--lang", "en", "setup", "--auto"]) == 0
    cap = capsys.readouterr()
    out = cap.out
    assert KEY not in out and KEY not in cap.err
    assert "claude-opus-5-5" in out and "available (not tested)" in out
    assert "Mode: lunovant" in out and str(_settings()) in out and "lunovant-settings.json" in out
    assert "Run `claude`" in out and "12.5💎" in out
    assert "[Codex]" not in out
    # mode switching by line
    assert cli.main(["--lang", "en", "mode"]) == 0
    assert "Claude Code: lunovant" in capsys.readouterr().out
    assert cli.main(["--lang", "en", "--yes", "mode", "personal", "--line", "claude"]) == 0
    assert "Claude Code mode: personal" in capsys.readouterr().out
    assert svc.claude_current_mode() == "personal"
    assert cli.main(["--lang", "en", "--yes", "mode", "lunovant"]) == 0
    assert svc.claude_current_mode() == "lunovant"


def test_cli_both_lines_and_keep_personal(svc, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    cli._SEEN_SECRETS.clear()
    real = svc.one_click_setup
    client = make_client(GPT + CLAUDE)
    monkeypatch.setattr(svc, "one_click_setup", lambda *a, **kw: real(*a, client=client, **kw))
    _write_settings(ORIGINAL)
    raw = _settings().read_bytes()
    _stdin(monkeypatch, KEY + "\n")
    assert cli.main(["--lang", "en", "setup", "--auto", "--keep-personal"]) == 0
    out = capsys.readouterr().out
    assert "[Codex]" in out and "[Claude Code]" in out and KEY not in out
    assert _settings().read_bytes() == raw  # kept personal: settings.json untouched
    assert svc.claude_current_mode() == "personal"
    assert cli.main(["--lang", "en", "--yes", "mode", "lunovant"]) == 0  # all installed lines
    assert svc.claude_current_mode() == "lunovant" and svc.current_mode() == "lunovant"


def test_cli_help_and_version():
    assert cli.build_parser().description.startswith("Lunovant Setup")
    from codex_setup import __version__
    assert __version__ == "0.4.1"
    from codex_setup.gui.app import TITLE
    assert TITLE == "Lunovant Setup"


# -- review fixes -----------------------------------------------------------------------------
def test_claude_probe_never_follows_redirects():
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(307, headers={"location": "https://evil.example/v1/messages"})

    c = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    res = model_probe.probe_claude_models("https://api.lunovant.tech/v1", KEY, ["claude-opus-5-5"], client=c)
    assert res[0]["ok"] is False and res[0]["status_code"] == 307
    assert [r.url.host for r in seen] == ["api.lunovant.tech"]
    assert not any(KEY in v for r in seen if r.url.host != "api.lunovant.tech" for v in r.headers.values())


FOREIGN = json.dumps({"theme": "dark", "env": {
    "ANTHROPIC_BASE_URL": "https://other.example", "ANTHROPIC_AUTH_TOKEN": "other-token-123",
    "ANTHROPIC_MODEL": "other-model"}}, indent=2) + "\n"


def test_existing_token_restored_on_personal_and_uninstall(svc):
    _write_settings(FOREIGN)
    raw = _settings().read_bytes()
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    assert "other-token-123" not in json.dumps(load_state().claude)
    data = json.loads(_settings().read_text())
    data["theme"] = "light"  # user edits another field: exact-original shortcut no longer applies
    _settings().write_text(json.dumps(data, indent=2))
    svc.claude_set_mode("personal")
    env = _env_of(_settings())
    assert env["ANTHROPIC_AUTH_TOKEN"] == "other-token-123"
    assert env["ANTHROPIC_BASE_URL"] == "https://other.example" and env["ANTHROPIC_MODEL"] == "other-model"
    svc.claude_set_mode("lunovant")
    assert _env_of(_settings())["ANTHROPIC_AUTH_TOKEN"] == KEY
    svc.uninstall()
    out = json.loads(_settings().read_text())
    assert out["theme"] == "light" and out["env"]["ANTHROPIC_AUTH_TOKEN"] == "other-token-123"
    assert KEY not in _settings().read_text()
    assert raw  # original bytes were non-empty


def test_failed_write_keeps_ownership_for_retry(svc, monkeypatch):
    _write_settings(ORIGINAL)
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    real = claude_config.write_private

    def boom(path, text):
        raise OSError("denied")

    monkeypatch.setattr(claude_config, "write_private", boom)
    with pytest.raises(Exception):
        svc.claude_set_mode("personal")
    assert load_state().claude["written"]
    monkeypatch.setattr(claude_config, "write_private", real)
    svc.claude_set_mode("personal")
    assert svc.claude_current_mode() == "personal"
    # uninstall: a failed settings write keeps ownership too
    svc.claude_set_mode("lunovant")
    monkeypatch.setattr(claude_config, "write_private", boom)
    with pytest.raises(Exception):
        svc.uninstall()
    monkeypatch.setattr(claude_config, "write_private", real)
    assert load_state().claude is not None
    svc.uninstall()
    assert load_state().claude is None and KEY not in _settings().read_text()


def test_command_uses_real_profile_path_with_spaces(svc, monkeypatch, tmp_path):
    d = tmp_path / "my claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(d))
    res = svc.one_click_setup(KEY, client=make_client(CLAUDE), mode="personal")
    # svc pretends to be macOS, so the path is POSIX-quoted even on a Windows runner.
    expected = f"claude --settings {shlex.quote(str(d / 'lunovant-settings.json'))}"
    assert expected in res.message
    assert svc.claude_launch_command("personal") == expected
    assert GuiApi(svc, lang="en").status()["claude"]["profile_command"] == svc.claude_launch_command("personal")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert svc.claude_launch_command("personal") == "claude --settings ~/.claude/lunovant-settings.json"


def test_uninstall_keeps_modified_profile(svc):
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    data = json.loads(_profile().read_text())
    data["note"] = "mine"
    _profile().write_text(json.dumps(data))
    res = svc.uninstall()
    assert _profile().exists() and any(k == "un_claude_profile_changed" for k, _ in res.notes)
    assert load_state().claude is None


def test_invalid_settings_leaves_profile_and_state_untouched(svc):
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    prof = _profile().read_text()
    state = (paths.app_state_dir() / "state.json").read_text()
    _write_settings("{ broken")
    with pytest.raises(Exception):
        svc.one_click_setup(KEY, client=make_client(CLAUDE, fail={"claude-opus-5-5"}))
    assert _profile().read_text() == prof
    assert (paths.app_state_dir() / "state.json").read_text() == state


def test_commit_failure_restores_previous_profile(svc, monkeypatch):
    _write_settings(ORIGINAL)
    svc.one_click_setup(KEY, client=make_client(CLAUDE))
    prof = _profile().read_text()
    real = claude_config.write_private

    def flaky(path, text):
        if path == _settings():
            raise OSError("denied")
        return real(path, text)

    monkeypatch.setattr(claude_config, "write_private", flaky)
    with pytest.raises(Exception):
        svc.one_click_setup(KEY, client=make_client(CLAUDE, fail={"claude-opus-5-5"}))
    assert _profile().read_text() == prof
