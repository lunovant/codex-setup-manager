"""Regression tests for the verified review findings (Task F)."""
from __future__ import annotations

import io
import json
import sys
import time
import types

import httpx
import pytest

from codex_setup import main as cli
from codex_setup.app import SetupService
from codex_setup.core import config_store, paths
from codex_setup.core.errors import (
    ConfigParseError,
    ConfigWriteError,
    SecretStoreError,
    ValidationError,
)
from codex_setup.core.config_store import load_config, save_config
from codex_setup.core.state import AppState, load_state, save_state
from codex_setup.diagnostics.api_test import Outcome, check_sse_stream, run_api_test
from codex_setup.diagnostics.checks import DiagnosticsContext, run_checks
from codex_setup.platforms import shellrc, windows
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.providers.catalog import normalize_base_url
from codex_setup.security.redact import redact_config_text
from codex_setup.security.secrets import SecretStore
from codex_setup.ui import i18n

KEY = "sk-fake-0000111122223333"


@pytest.fixture
def svc() -> SetupService:
    s = SetupService(secret_store=SecretStore(backend="session"))
    s._platform = PlatformInfo("macos", "25", "arm64")
    s._install = CodexInstall(None, None, False, False, None, None, "n/a")
    return s


def _cfg():
    return paths.config_path()


def _write(text: str) -> None:
    _cfg().parent.mkdir(parents=True, exist_ok=True)
    _cfg().write_text(text, encoding="utf-8")


# 1 ---------------------------------------------------------------------------
def test_redact_config_text_masks_sensitive_keys():
    text = (
        '+Authorization = "Bearer abcdefghijkl"\n'
        '+http_headers = { "X-Api-Key" = "zzzzzzzzzzzz", Accept = "json" }\n'
        '+experimental_bearer_token = "tok-123456789"\n'
        '+password = "hunter2hunter2"\n'
        '+base_url = "https://x/v1"\n'
        "+note = sk-known-secret-9999\n"
    )
    out = redact_config_text(text, ["sk-known-secret-9999"])
    for leaked in ("abcdefghijkl", "zzzzzzzzzzzz", "tok-123456789", "hunter2hunter2", "sk-known-secret-9999"):
        assert leaked not in out
    assert 'Accept = "json"' in out and "https://x/v1" in out


def test_cli_diff_redacts_but_disk_keeps_content(svc, capsys, monkeypatch):
    _write('model = "m"\n\n[model_providers.x]\nname = "X"\nbase_url = "https://x/v1"\n'
           'env_key = "X_KEY"\nhttp_headers = { Authorization = "Bearer topsecretvalue1" }\n')
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli.main(["setup", "--dry-run"]) == 0
    assert "topsecretvalue1" not in capsys.readouterr().out
    assert "topsecretvalue1" in _cfg().read_text()


# 2 ---------------------------------------------------------------------------
def test_sandbox_log_redacts_env_secrets(tmp_path):
    home = tmp_path / "ch"
    (home / ".sandbox").mkdir(parents=True)
    (home / ".sandbox" / "sandbox.log").write_text("error: bad token ENVSECRET-12345678 and OTHER_TOKEN_VALUE_99\n")
    cfg = tmp_path / "config.toml"
    cfg.write_text('model_provider = "p"\n[model_providers.p]\nname="p"\nbase_url="https://x/v1"\nenv_key="P_KEY"\n')
    env = {"CODEX_HOME": str(home), "P_KEY": "ENVSECRET-12345678", "SOME_API_KEY": "OTHER_TOKEN_VALUE_99"}
    ctx = DiagnosticsContext(cfg, env, PlatformInfo("windows", "11", "x"),
                             CodexInstall(None, None, False, False, None, None, "n/a"),
                             AppState(), SecretStore("session"))
    out = repr(run_checks(ctx))
    assert "ENVSECRET-12345678" not in out and "OTHER_TOKEN_VALUE_99" not in out


# 3 ---------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["https://u:p@api.x.tech/v1", "https://api.x.tech/v1?key=abc", "https://api.x.tech/v1?"])
def test_base_url_rejects_userinfo_and_query(url):
    with pytest.raises(ValidationError) as ei:
        normalize_base_url(url)
    msg = str(ei.value)
    assert "u:p" not in msg and "abc" not in msg and "api.x.tech" not in msg


def test_cli_api_rejects_credential_url(svc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    assert cli.main(["api", "--base-url", "https://u:p@api.x.tech/v1", "--yes"]) == 1
    assert "u:p" not in capsys.readouterr().err


# 4 ---------------------------------------------------------------------------
def test_state_is_per_config_path(svc, tmp_path, monkeypatch):
    svc.quick_setup(None, "gpt-6.1-sol", None, "session")
    other = tmp_path / "other_codex"
    monkeypatch.setenv("CODEX_HOME", str(other))
    assert svc.ownership().managed_provider_ids == []
    assert len(load_state().configs) == 1
    r = svc.uninstall()  # nothing owned for the other config
    assert not r.changed
    assert len(load_state().configs) == 1


def test_legacy_flat_state_migrated_only_if_config_exists(isolated_env):
    legacy = {"version": 1, "managed_provider_ids": ["lunovant"],
              "original_top_level": {"model": None, "model_provider": None}, "original_snapshot": ""}
    path = paths.app_state_dir(isolated_env) / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(legacy))
    assert load_state(isolated_env).configs == {}
    _write('model = "a"\n')
    st = load_state(isolated_env)
    (own,) = st.configs.values()
    assert own.managed_provider_ids == ["lunovant"]


# 5 ---------------------------------------------------------------------------
def test_originals_recorded_before_key_store_and_survive_failure(svc, monkeypatch):
    _write('model = "orig"\n')

    def boom(*a, **k):
        raise SecretStoreError("nope")

    with monkeypatch.context() as m:  # never monkeypatch.undo(): it would drop env isolation
        m.setattr(svc.secret_store(), "set", boom)
        with pytest.raises(SecretStoreError):
            svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    assert _cfg().read_text() == 'model = "orig"\n'  # config written last -> untouched
    own = svc.ownership()
    assert own.original_top_level == {"model": "orig", "model_provider": None}
    svc.quick_setup(None, "gpt-6-luna", "k-1234567890", "session")
    assert svc.ownership().original_top_level == {"model": "orig", "model_provider": None}


# 6 ---------------------------------------------------------------------------
def test_lost_update_guard(isolated_env):
    _write('model = "a"\n')
    loaded = load_config(_cfg())
    loaded.doc["model"] = "b"
    _cfg().write_text('model = "edited-by-user"\n')
    with pytest.raises(ConfigWriteError, match="changed on disk"):
        save_config(loaded, env=isolated_env)
    assert _cfg().read_text() == 'model = "edited-by-user"\n'


def test_rollback_does_not_clobber_foreign_write(isolated_env, monkeypatch):
    _write('model = "a"\n')
    loaded = load_config(_cfg())
    loaded.doc["model"] = "b"
    real = config_store.atomic_write_text

    def racing(path, text):
        real(path, 'model = "foreign"\n')  # someone else wrote; verification will mismatch

    monkeypatch.setattr(config_store, "atomic_write_text", racing)
    with pytest.raises(ConfigWriteError):
        save_config(loaded, env=isolated_env)
    assert _cfg().read_text() == 'model = "foreign"\n'


# 7 ---------------------------------------------------------------------------
def test_windows_ctypes_prototypes(monkeypatch):
    import ctypes

    class Fn:
        def __call__(self, *a):
            self.args = a
            return 1

    fn = Fn()
    monkeypatch.setattr(ctypes, "windll",
                        types.SimpleNamespace(user32=types.SimpleNamespace(SendMessageTimeoutW=fn)),
                        raising=False)
    windows.broadcast_env_change()
    assert fn.argtypes[3] is ctypes.c_wchar_p and len(fn.argtypes) == 7
    assert isinstance(fn.args[6]._obj, ctypes.c_size_t)


# 8 ---------------------------------------------------------------------------
def test_session_key_visible_across_calls_in_one_service(isolated_env):
    s = SetupService()
    s._platform = PlatformInfo("macos", "25", "arm64")
    s.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    assert s.get_key("LUNOVANT_API_KEY") == "k-1234567890"
    assert s.secret_store() is s.secret_store("session")


def test_cli_warns_when_session_backend(svc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    monkeypatch.setattr("sys.stdin", io.StringIO(KEY + "\n"))
    i18n.set_lang("en")
    assert cli.main(["setup", "--yes", "--key-stdin", "--secret-backend", "session"]) == 0
    err = capsys.readouterr().err
    assert "memory" in err and "launch" in err and KEY not in err


# 9 ---------------------------------------------------------------------------
def test_uninstall_restores_overwritten_fields(svc):
    _write('[model_providers.lunovant]\nname = "Mine"\nbase_url = "https://mine/v1"\n'
           'env_key = "MINE_KEY"\n')
    svc.quick_setup(None, "gpt-6.1-sol", None, "session")
    assert svc.ownership().managed_provider_ids == []
    svc.uninstall()
    import tomllib
    tbl = tomllib.loads(_cfg().read_text())["model_providers"]["lunovant"]
    assert tbl == {"name": "Mine", "base_url": "https://mine/v1", "env_key": "MINE_KEY"}


def test_uninstall_leaves_user_changed_field(svc):
    _write('[model_providers.lunovant]\nname = "Mine"\nbase_url = "https://mine/v1"\n'
           'env_key = "MINE_KEY"\n')
    svc.quick_setup(None, "gpt-6.1-sol", None, "session")
    text = _cfg().read_text().replace('name = "Lunovant"', 'name = "Edited"')
    _cfg().write_text(text)
    res = svc.uninstall()
    import tomllib
    tbl = tomllib.loads(_cfg().read_text())["model_providers"]["lunovant"]
    assert tbl["name"] == "Edited" and tbl["base_url"] == "https://mine/v1"
    assert any(k == "un_field_changed" for k, _ in res.notes)


# 10 --------------------------------------------------------------------------
def test_uninstall_delete_key_removes_all_owned_keys(svc):
    svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    store = svc.secret_store()
    store.set("OTHER_KEY", "not-ours-123456")
    res = svc.uninstall(delete_secret=True)
    assert store.get("LUNOVANT_API_KEY") is None
    assert store.get("OTHER_KEY") == "not-ours-123456"
    assert ("un_keys_deleted", {"keys": "LUNOVANT_API_KEY"}) in res.notes


# 11 --------------------------------------------------------------------------
def test_env_install_remove_restores_previous_rc_block(svc, tmp_path):
    svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    svc._env = {**__import__("os").environ, "HOME": str(tmp_path / "h"), "SHELL": "/bin/zsh"}
    (tmp_path / "h").mkdir()
    rc = tmp_path / "h" / ".zshrc"
    rc.write_text("alias a=b\n")
    svc.env_install(True)
    assert shellrc.has_block(rc)
    assert svc.env_remove() == "removed"
    assert rc.read_text() == "alias a=b\n"
    assert svc.env_remove() == "not_owned"


def test_env_remove_not_owned_when_user_has_own_block(svc, tmp_path):
    svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    svc._env = {**__import__("os").environ, "HOME": str(tmp_path / "h"), "SHELL": "/bin/zsh"}
    (tmp_path / "h").mkdir()
    rc = tmp_path / "h" / ".zshrc"
    shellrc.install_block(rc, "LUNOVANT_API_KEY", "user-own-value")
    before = rc.read_text()
    assert svc.env_remove() == "not_owned"
    assert rc.read_text() == before


def test_windows_env_install_records_and_restores(svc, monkeypatch):
    store = {"LUNOVANT_API_KEY": ("old-value", 2)}
    m = types.ModuleType("winreg")
    m.HKEY_CURRENT_USER, m.KEY_READ, m.KEY_SET_VALUE, m.REG_SZ = 1, 1, 2, 1

    class K:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    m.OpenKey = lambda *a: K()
    m.CreateKeyEx = lambda *a: K()

    def q(k, n):
        if n not in store:
            raise FileNotFoundError(n)
        return store[n]

    m.QueryValueEx = q
    m.SetValueEx = lambda k, n, _r, typ, v: store.__setitem__(n, (v, typ))
    m.DeleteValue = lambda k, n: store.pop(n)
    monkeypatch.setitem(sys.modules, "winreg", m)
    monkeypatch.setattr(windows, "broadcast_env_change", lambda: None)
    svc._platform = PlatformInfo("windows", "11", "x")
    svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    svc.env_install(True)
    assert store["LUNOVANT_API_KEY"] == ("k-1234567890", 1)
    assert svc.env_remove() == "restored"
    assert store["LUNOVANT_API_KEY"] == ("old-value", 2)


# 12 --------------------------------------------------------------------------
def test_dry_run_mutations_change_nothing(svc, tmp_path, monkeypatch):
    svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    state_before = (paths.app_state_dir() / "state.json").read_text()
    cfg_before = _cfg().read_text()
    svc.add_profile("acme", "https://acme/v1", "ACME_KEY", dry_run=True)
    svc.add_custom_model("zzz", dry_run=True)
    svc.set_api(api_key="new-key-123456", dry_run=True)
    svc.set_api(delete_key=True, dry_run=True)
    svc.backup_create(dry_run=True)
    svc.uninstall(dry_run=True, delete_secret=True)
    assert (paths.app_state_dir() / "state.json").read_text() == state_before
    assert _cfg().read_text() == cfg_before
    assert svc.secret_store().get("LUNOVANT_API_KEY") == "k-1234567890"
    assert svc.backup_list() == []


def test_cli_dry_run_profile_and_backup(svc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    svc.quick_setup(None, "gpt-6.1-sol", None, "session")
    before = (paths.app_state_dir() / "state.json").read_text()
    assert cli.main(["profile", "add", "acme", "--base-url", "https://a/v1", "--env-key", "A_KEY", "--dry-run"]) == 0
    assert cli.main(["backup", "create", "--dry-run"]) == 0
    assert (paths.app_state_dir() / "state.json").read_text() == before
    assert svc.backup_list() == []


# 13 --------------------------------------------------------------------------
def _sse(*records: str):
    for rec in records:
        yield from rec.split("\n")
        yield ""


def _dl(sec=5.0):
    return time.monotonic() + sec


def test_sse_ok():
    v = check_sse_stream(_sse('event: response.created\ndata: {"type":"response.created"}',
                              'data: {"type":"response.completed"}'), KEY, deadline=_dl())
    assert v.outcome == Outcome.OK


def test_sse_completed_before_created_fails():
    v = check_sse_stream(_sse('data: {"type":"response.completed"}',
                              'data: {"type":"response.created"}'), KEY, deadline=_dl())
    assert v.outcome == Outcome.FAIL and v.code == "at_stream_no_start"


def test_sse_error_event_fails_with_redacted_message():
    v = check_sse_stream(
        _sse('event: error\ndata: {"type":"error","error":{"message":"bad key %s"}}' % KEY),
        KEY, deadline=_dl())
    assert v.outcome == Outcome.FAIL and v.code == "at_stream_error" and KEY not in v.detail


def test_sse_failed_event():
    v = check_sse_stream(_sse('data: {"type":"response.created"}',
                              'data: {"type":"response.failed","response":{"error":{"message":"boom"}}}'),
                         KEY, deadline=_dl())
    assert v.outcome == Outcome.FAIL and "boom" in v.detail


def test_sse_heartbeat_forever_hits_deadline():
    def forever():
        while True:
            yield ": ping"
            yield ""
            time.sleep(0.001)

    v = check_sse_stream(forever(), KEY, deadline=time.monotonic() + 0.05)
    assert v.outcome == Outcome.FAIL and v.code == "at_stream_deadline"


def test_sse_size_cap():
    def big():
        while True:
            yield ": " + "x" * 10000

    v = check_sse_stream(big(), KEY, deadline=_dl(), max_bytes=50_000)
    assert v.code == "at_stream_too_big"


def test_sse_stops_after_terminal_event():
    consumed = []

    def gen():
        for line in ['data: {"type":"response.created"}', "",
                     'data: {"type":"response.completed"}', "", "NEVER READ", ""]:
            consumed.append(line)
            yield line

    assert check_sse_stream(gen(), KEY, deadline=_dl()).outcome == Outcome.OK
    assert "NEVER READ" not in consumed


def test_run_api_test_stream_error_event():
    sse = 'event: error\ndata: {"type":"error","error":{"message":"quota"}}\n\n'

    def handler(req):
        p = req.url.path
        if p == "/":
            return httpx.Response(200, text="hi")
        if p.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m1"}]})
        if json.loads(req.content).get("stream"):
            return httpx.Response(200, text=sse)
        return httpx.Response(200, json={"object": "response", "output": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        rep = run_api_test("https://api.example.com/v1", KEY, "m1", client=c)
    s = next(x for x in rep.steps if x.step == "responses_stream")
    assert s.outcome == Outcome.FAIL and "quota" in s.detail and rep.overall == Outcome.FAIL


# 14 --------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    'model_providers = "x"\n',
    '[model_providers]\nfoo = "bar"\n',
    "model = 5\n",
    "model_provider = true\n",
    'windows = "x"\n',
])
def test_schema_validation(text):
    from codex_setup.core import codex_config

    _write(text)
    with pytest.raises(ConfigParseError):
        codex_config.get_status(load_config(_cfg()).doc)


@pytest.mark.parametrize("bad", [
    {"profiles": []},
    {"active_profile": 5},
    {"configs": {"/x": {"managed_provider_ids": "lunovant"}}},
    {"configs": {"/x": {"credentials": {"keyring": "K"}}}},
])
def test_malformed_state_is_corrupt(isolated_env, bad):
    path = paths.app_state_dir(isolated_env) / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(bad))
    assert load_state(isolated_env) == AppState()
    assert (path.parent / "state.json.bad").exists()


def test_unexpected_exception_is_redacted_one_liner(svc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    monkeypatch.setattr(svc, "status", lambda: (_ for _ in ()).throw(RuntimeError("oops " + KEY)))
    monkeypatch.delenv("CODEX_SETUP_DEBUG", raising=False)
    cli._SEEN_SECRETS[:] = [KEY]
    assert cli.main(["status"]) == 1
    err = capsys.readouterr().err
    assert KEY not in err and "CODEX_SETUP_DEBUG=1" in err and "Traceback" not in err
    monkeypatch.setenv("CODEX_SETUP_DEBUG", "1")
    assert cli.main(["status"]) == 1
    err = capsys.readouterr().err
    assert KEY not in err and "Traceback" in err
    cli._SEEN_SECRETS.clear()


# 15 --------------------------------------------------------------------------
def test_file_backend_requires_confirmation(svc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    i18n.set_lang("en")
    assert cli.main(["setup", "--secret-backend", "file"]) == 1  # non-interactive, no --yes
    cap = capsys.readouterr()
    assert "PLAINTEXT" in cap.err and not _cfg().exists()
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli.main(["setup", "--secret-backend", "file", "--yes"]) == 0


# 16 --------------------------------------------------------------------------
def test_i18n_keys_in_both_languages():
    assert set(i18n.EN) == set(i18n.VI)


def test_vi_test_and_diagnose_output_are_vietnamese(svc, capsys, monkeypatch):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    assert cli.main(["--lang", "vi", "diagnose"]) in (0, 1)
    out = capsys.readouterr().out
    assert "Không tìm thấy config.toml" in out and "Cách sửa" in out
    from codex_setup.diagnostics.api_test import ApiTestReport, Problem, StepResult

    rep = ApiTestReport([StepResult("connect", Outcome.FAIL, Problem.DNS, "DNS lookup failed",
                                    code="at_dns")], Outcome.FAIL)
    i18n.set_lang("vi")
    assert "Không phân giải" in "\n".join(cli.render_report_lines(rep))
    i18n.set_lang("en")
