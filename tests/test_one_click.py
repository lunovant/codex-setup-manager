from __future__ import annotations

import io
import os
import tomllib

import httpx
import pytest

from codex_setup import main as cli
from codex_setup.app import SetupService
from codex_setup.core import paths
from codex_setup.core.state import load_state
from codex_setup.diagnostics import model_probe
from codex_setup.diagnostics.checks import DiagnosticsContext, run_checks
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.redact import redact_config_text
from codex_setup.security.secrets import SecretStore

KEY = "sk-lunovant-SECRET-1234567890"
BASE = "https://api.lunovant.tech/v1"
USAGE_OK = {"isValid": True, "status": "active", "expires_at": "2099-01-01T00:00:00Z",
            "days_until_expiry": 900, "remaining": 12.5, "planName": "Pro"}
ALL = ["gpt-6.1-sol", "gpt-6-luna", "codex-auto-review"]


def make_client(*, usage=None, models=None, fail=(), usage_status=200, models_status=200):
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        assert req.headers["authorization"] == f"Bearer {KEY}"
        p = req.url.path
        if p == "/v1/usage":
            return httpx.Response(usage_status, json=usage if usage is not None else USAGE_OK)
        if p == "/v1/models":
            body = {"data": [{"id": m} for m in (ALL if models is None else models)]}
            return httpx.Response(models_status, json=body)
        if p == "/v1/responses":
            import json
            model = json.loads(req.content)["model"]
            if model in fail:
                return httpx.Response(429, text="slow down")
            return httpx.Response(200, json={"object": "response", "output": []})
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


# -- model_probe -------------------------------------------------------------
@pytest.mark.parametrize("body", [
    {"data": [{"id": "a"}, {"id": "b"}, {"id": "a"}, {"id": "codex-auto-review"}]},
    {"models": [{"name": "a"}, {"id": "b"}]},
    ["a", {"id": "b"}, "a"],
])
def test_fetch_models_variants(body):
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    assert model_probe.fetch_models(BASE, KEY, client=c) == ["a", "b"]


def test_fetch_models_failure_is_empty():
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    assert model_probe.fetch_models(BASE, KEY, client=c) == []


def test_probe_models_one_failing():
    c = make_client(fail={"gpt-6-luna"})
    res = model_probe.probe_models(BASE, KEY, ["gpt-6.1-sol", "gpt-6-luna"], client=c)
    assert [r["model"] for r in res] == ["gpt-6.1-sol", "gpt-6-luna"]
    assert res[0]["ok"] and res[0]["status_code"] == 200 and res[0]["latency_ms"] is not None
    assert not res[1]["ok"] and res[1]["status_code"] == 429 and "429" in res[1]["error"]
    assert KEY not in repr(res)


def test_probe_timeout():
    def boom(req):
        raise httpx.ReadTimeout("slow")

    c = httpx.Client(transport=httpx.MockTransport(boom))
    res = model_probe.probe_models(BASE, KEY, ["m"], client=c)
    assert res[0]["error"] == "timeout" and not res[0]["ok"]


def test_check_key_variants():
    info = model_probe.check_key(BASE, KEY, client=make_client())
    assert info["valid"] and not info["expired"] and info["plan"] == "Pro"
    assert info["remaining"] == 12.5 and info["days_left"] == 900
    exp = model_probe.check_key(BASE, KEY, client=make_client(usage={"status": "expired"}))
    assert exp["expired"] and exp["valid"]
    past = model_probe.check_key(
        BASE, KEY, client=make_client(usage={"isValid": True, "expires_at": "2020-01-01T00:00:00Z"}))
    assert past["expired"]
    bad = model_probe.check_key(BASE, KEY, client=make_client(usage_status=401))
    assert not bad["valid"]


# -- one_click_setup -----------------------------------------------------------
def _cfg():
    return paths.config_path()


def test_happy_path(svc):
    steps: list[str] = []
    res = svc.one_click_setup(f" {KEY}​\n", progress=lambda s, d: steps.append(s),
                              client=make_client())
    assert res.ok and res.code == "ok" and res.default_model == "gpt-6.1-sol"
    assert [m["model"] for m in res.models] == ["gpt-6.1-sol", "gpt-6-luna"]
    assert steps[0] == "check_key" and steps[-1] == "done"
    assert {"fetch_models", "probe:gpt-6.1-sol", "probe:gpt-6-luna", "write_config"} <= set(steps)
    text = _cfg().read_text()
    data = tomllib.loads(text)
    prov = data["model_providers"]["lunovant"]
    assert prov["experimental_bearer_token"] == KEY
    assert "env_key" not in prov and prov["wire_api"] == "responses" and prov["base_url"] == BASE
    assert data["model"] == "gpt-6.1-sol" and data["model_provider"] == "lunovant"
    if os.name == "posix":
        assert (_cfg().stat().st_mode & 0o777) == 0o600
    state_text = (paths.app_state_dir() / "state.json").read_text()
    assert KEY not in state_text
    st = load_state()
    assert st.one_click and st.one_click["models"] == ["gpt-6.1-sol", "gpt-6-luna"]
    assert svc.available_models()[:2] == ["gpt-6.1-sol", "gpt-6-luna"]
    assert svc.secret_store().get("LUNOVANT_API_KEY") == KEY


def test_replaces_env_key_and_fallback_default(svc):
    cfg = _cfg()
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[model_providers.lunovant]\nname = "Lunovant"\nbase_url = "x"\n'
                   'env_key = "LUNOVANT_API_KEY"\nwire_api = "responses"\n')
    res = svc.one_click_setup(KEY, client=make_client(fail={"gpt-6.1-sol"}))
    assert res.ok and res.default_model == "gpt-6-luna"
    assert res.backup_path is not None
    prov = tomllib.loads(cfg.read_text())["model_providers"]["lunovant"]
    assert "env_key" not in prov and prov["experimental_bearer_token"] == KEY
    assert prov["base_url"] == BASE
    assert svc.set_default_model("gpt-6.1-sol").changed
    assert tomllib.loads(cfg.read_text())["model"] == "gpt-6.1-sol"


@pytest.mark.parametrize("kw,code", [
    ({"usage_status": 401}, "key_invalid"),
    ({"usage": {"isValid": False, "status": "expired", "expires_at": "2020-01-01"}}, "key_expired"),
    ({"models": ["whisper-1", "text-embedding-3"]}, "not_codex_key"),
    ({"models": []}, "not_codex_key"),
    ({"fail": {"gpt-6.1-sol", "gpt-6-luna"}}, "no_model_works"),
])
def test_stops_without_writing(svc, kw, code):
    res = svc.one_click_setup(KEY, client=make_client(**kw))
    assert not res.ok and res.code == code
    assert not _cfg().exists()
    if code == "no_model_works":
        assert len(res.models) == 2
    if code == "key_expired":
        assert "2020-01-01" in res.message


# -- redaction / diagnostics ------------------------------------------------------
def test_redact_masks_token():
    text = f'[model_providers.x]\nexperimental_bearer_token = "{KEY}"\n'
    out = redact_config_text(text, [])
    assert KEY not in out and "****" in out


def test_diagnostics_no_env_unset_with_bearer(svc):
    svc.one_click_setup(KEY, client=make_client())
    ctx = DiagnosticsContext(_cfg(), {}, svc.platform, svc.install, load_state(),
                             SecretStore(backend="session"))
    ids = {r.code for r in run_checks(ctx)}
    assert "dgc_env_var_unset" not in ids and "dgc_env_key_missing" not in ids


# -- CLI ---------------------------------------------------------------------------
def test_cli_setup_key_stdin(svc, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    cli._SEEN_SECRETS.clear()
    monkeypatch.setattr(model_probe, "check_key", lambda *a, **k: dict(USAGE_OK, valid=True, expired=False))
    monkeypatch.setattr(model_probe, "fetch_models", lambda *a, **k: ["gpt-6.1-sol"])
    monkeypatch.setattr(
        model_probe, "probe_models",
        lambda *a, **k: [{"model": "gpt-6.1-sol", "ok": True, "latency_ms": 5,
                          "status_code": 200, "error": None}])
    monkeypatch.setattr("sys.stdin", io.StringIO(KEY + "\n"))
    assert cli.main(["--lang", "en", "setup", "--auto"]) == 0
    out = capsys.readouterr().out
    assert "gpt-6.1-sol" in out and "Default model" in out and KEY not in out
    assert tomllib.loads(_cfg().read_text())["model_providers"]["lunovant"][
        "experimental_bearer_token"] == KEY


def test_cli_setup_key_invalid(svc, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    monkeypatch.setattr(model_probe, "check_key", lambda *a, **k: {"valid": False, "expired": False})
    monkeypatch.setattr("sys.stdin", io.StringIO(KEY + "\n"))
    assert cli.main(["--lang", "en", "setup", "--auto"]) == 1
    cap = capsys.readouterr()
    assert "key_invalid" in cap.err and KEY not in cap.err
    assert not _cfg().exists()


# -- review fixes ---------------------------------------------------------------------
def test_cli_dry_run_refused_and_writes_nothing(svc, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    called = []
    monkeypatch.setattr(svc, "one_click_setup", lambda *a, **k: called.append(1))
    assert cli.main(["--lang", "en", "setup", "--auto", "--dry-run"]) == 2
    assert not called and not _cfg().exists()
    assert not (paths.app_state_dir() / "state.json").exists()
    assert svc.secret_store().get("LUNOVANT_API_KEY") is None
    assert KEY not in capsys.readouterr().err


@pytest.mark.skipif(os.name != "posix", reason="POSIX modes")
def test_token_file_private_before_replace(svc, monkeypatch):
    cfg = _cfg()
    cfg.parent.mkdir(parents=True)
    cfg.write_text('model = "x"\n')
    cfg.chmod(0o644)
    modes = []
    real = os.replace

    def spy(src, dst):
        if str(dst) == str(cfg):
            modes.append(os.stat(src).st_mode & 0o777)
        return real(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    assert svc.one_click_setup(KEY, client=make_client()).ok
    assert modes and all(m == 0o600 for m in modes)
    assert (cfg.stat().st_mode & 0o777) == 0o600
    for b in paths.backups_dir().glob("*.toml"):
        assert (b.stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX modes")
def test_chmod_failure_is_not_swallowed(svc, monkeypatch):
    from codex_setup.core.errors import ConfigWriteError

    def boom(*a, **k):
        raise PermissionError("no")

    monkeypatch.setattr(os, "chmod", boom)
    with pytest.raises(ConfigWriteError):
        svc.one_click_setup(KEY, client=make_client())


PRE = ('[model_providers.lunovant]\nname = "L"\nbase_url = "https://old/v1"\n'
       'env_key = "LUNOVANT_API_KEY"\nwire_api = "responses"\n')


def test_uninstall_removes_new_token_on_existing_provider(svc):
    cfg = _cfg()
    cfg.parent.mkdir(parents=True)
    cfg.write_text(PRE)
    assert svc.one_click_setup(KEY, client=make_client()).ok
    assert KEY not in (paths.app_state_dir() / "state.json").read_text()
    svc.uninstall(delete_secret=True)
    text = cfg.read_text()
    assert KEY not in text and "experimental_bearer_token" not in text
    prov = tomllib.loads(text)["model_providers"]["lunovant"]
    assert prov["env_key"] == "LUNOVANT_API_KEY" and prov["base_url"] == "https://old/v1"
    assert svc.secret_store().get("LUNOVANT_API_KEY") is None


def test_uninstall_restores_previous_token(svc):
    cfg = _cfg()
    cfg.parent.mkdir(parents=True)
    cfg.write_text(PRE.replace('env_key = "LUNOVANT_API_KEY"\n', 'experimental_bearer_token = "old-token-123456"\n'))
    assert svc.one_click_setup(KEY, client=make_client()).ok
    svc.uninstall(delete_secret=True)
    prov = tomllib.loads(cfg.read_text())["model_providers"]["lunovant"]
    assert prov["experimental_bearer_token"] == "old-token-123456"


def test_uninstall_keeps_token_user_changed(svc):
    cfg = _cfg()
    cfg.parent.mkdir(parents=True)
    cfg.write_text(PRE)
    assert svc.one_click_setup(KEY, client=make_client()).ok
    cfg.write_text(cfg.read_text().replace(KEY, "user-own-token-999"))
    svc.uninstall()
    assert "user-own-token-999" in cfg.read_text()


def _prov():
    return tomllib.loads(_cfg().read_text())["model_providers"]["lunovant"]


def test_use_profile_keeps_bearer_mode(svc):
    assert svc.one_click_setup(KEY, client=make_client()).ok
    svc.add_profile("other", "https://o.example/v1", "OTHER_KEY", "m1")
    svc.use_profile("lunovant")
    assert _prov()["experimental_bearer_token"] == KEY and "env_key" not in _prov()
    svc.use_profile("other")
    svc.use_profile("lunovant")
    assert _prov()["experimental_bearer_token"] == KEY and "env_key" not in _prov()
    assert tomllib.loads(_cfg().read_text())["model_provider"] == "lunovant"


def test_launch_after_one_click(svc, monkeypatch):
    assert svc.one_click_setup(KEY, client=make_client()).ok
    svc._install = CodexInstall("/bin/codex", "1", False, False, None, None, "n/a")
    seen = {}

    def fake(args, env_key, secret, *, codex_path, run=None):
        seen.update(env_key=env_key, secret=secret)
        return 0

    monkeypatch.setattr("codex_setup.app.launcher.launch_cli", fake)
    assert svc.launch("cli") == 0 and seen["secret"] == KEY


def test_launch_uses_config_token_when_store_empty(svc, monkeypatch):
    assert svc.one_click_setup(KEY, client=make_client()).ok
    svc.secret_store().delete("LUNOVANT_API_KEY")
    svc._install = CodexInstall("/bin/codex", "1", False, False, None, None, "n/a")
    seen = {}
    monkeypatch.setattr("codex_setup.app.launcher.launch_cli",
                        lambda a, e, s, *, codex_path, run=None: seen.setdefault("s", s) and 0)
    svc.launch("cli")
    assert seen["s"] == KEY


def test_gui_windows_launch_after_one_click(monkeypatch):
    from codex_setup.gui.api import GuiApi

    s = SetupService(secret_store=SecretStore(backend="session"))
    s._platform = PlatformInfo("windows", "11", "x64")  # type: ignore[arg-type]
    s._install = CodexInstall("C:/codex.exe", "1", False, False, None, None, "n/a")
    assert s.one_click_setup(KEY, client=make_client()).ok
    s.secret_store().delete("LUNOVANT_API_KEY")
    calls = []
    monkeypatch.setattr("codex_setup.gui.api.subprocess.Popen",
                        lambda *a, **k: calls.append(k))
    res = GuiApi(s, lang="en").launch("cli")
    assert res["ok"] and calls


def test_set_api_bearer_key_url_and_delete(svc):
    assert svc.one_click_setup(KEY, client=make_client()).ok
    svc.set_api(api_key="sk-new-KEY-0987654321")
    assert _prov()["experimental_bearer_token"] == "sk-new-KEY-0987654321"
    assert "env_key" not in _prov()
    assert svc.secret_store().get("LUNOVANT_API_KEY") == "sk-new-KEY-0987654321"
    svc.set_api(base_url="https://new.example/v1")
    assert _prov()["base_url"] == "https://new.example/v1"
    assert _prov()["experimental_bearer_token"] == "sk-new-KEY-0987654321" and "env_key" not in _prov()
    svc.set_api(delete_key=True)
    assert "experimental_bearer_token" not in _prov()
    assert svc.secret_store().get("LUNOVANT_API_KEY") is None
