from pathlib import Path

from codex_setup.core.state import AppState
from codex_setup.diagnostics.api_test import Outcome
from codex_setup.diagnostics.checks import DiagnosticsContext, run_checks
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.secrets import SecretStore

KEY = "sk-test-SECRET-1234567890"
GOOD = '''model = "m"
model_provider = "lunovant"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
env_key = "LUNOVANT_API_KEY"
wire_api = "responses"
'''


def ctx(tmp_path, text=None, env=None, system="linux", store=None, state=None):
    home = tmp_path / "ch"
    home.mkdir(exist_ok=True)
    cfg = home / "config.toml"
    if text is not None:
        cfg.write_text(text)
    inst = CodexInstall("/bin/codex", "0.1.0", True, False, None, None, "Desktop not found")
    return DiagnosticsContext(cfg, {"CODEX_HOME": str(home), **(env or {})}, PlatformInfo(system, "1", "x"),
                              inst, state or AppState(), store or SecretStore("session"))


def by_id(results):
    return {r.id: r for r in results}


def test_missing_config(tmp_path):
    r = by_id(run_checks(ctx(tmp_path)))
    assert r["config"].outcome == Outcome.WARN


def test_invalid_config(tmp_path):
    r = by_id(run_checks(ctx(tmp_path, "model = \n[x")))
    assert r["config"].outcome == Outcome.FAIL and "line" in r["config"].detail


def test_provider_mismatch(tmp_path):
    r = by_id(run_checks(ctx(tmp_path, 'model_provider = "ghost"\nmodel = "m"\n')))
    assert r["provider"].outcome == Outcome.FAIL and "ghost" in r["provider"].detail


def test_env_missing_but_stored(tmp_path):
    store = SecretStore("session")
    store.set("LUNOVANT_API_KEY", KEY)
    r = by_id(run_checks(ctx(tmp_path, GOOD, store=store)))
    assert r["env_var"].outcome == Outcome.WARN and "launch" in r["env_var"].fix
    assert r["secret"].outcome == Outcome.OK
    r = by_id(run_checks(ctx(tmp_path, GOOD, store=store, env={"LUNOVANT_API_KEY": "x"})))
    assert r["env_var"].outcome == Outcome.OK


def test_env_missing_and_not_stored(tmp_path):
    r = by_id(run_checks(ctx(tmp_path, GOOD)))
    assert r["env_var"].outcome == Outcome.FAIL and r["secret"].outcome == Outcome.WARN


def test_windows_sandbox_log(tmp_path):
    store = SecretStore("session")
    store.set("LUNOVANT_API_KEY", KEY)
    log = tmp_path / "ch" / ".sandbox" / "sandbox.log"
    log.parent.mkdir(parents=True)
    log.write_text(f"ok line\nERROR setup failed token={KEY}\nfine\n")
    text = GOOD + '\n[windows]\nsandbox = "elevated"\n'
    results = run_checks(ctx(tmp_path, text, system="windows", store=store))
    r = by_id(results)
    assert r["sandbox_mode"].outcome == Outcome.OK and "elevated" in r["sandbox_mode"].title
    assert r["sandbox_log"].outcome == Outcome.WARN
    assert "setup failed" in r["sandbox_log"].detail and KEY not in repr(results)


def test_non_windows_has_no_sandbox_checks(tmp_path):
    assert "sandbox_log" not in by_id(run_checks(ctx(tmp_path, GOOD)))


def test_last_test(tmp_path):
    st = AppState(last_test={"when": "t", "overall": "fail", "model": "m"})
    assert by_id(run_checks(ctx(tmp_path, GOOD, state=st)))["last_test"].outcome == Outcome.FAIL
