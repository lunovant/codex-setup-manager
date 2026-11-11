from __future__ import annotations

import io
import json
import tomllib
from pathlib import Path

import pytest

from codex_setup import main as cli
from codex_setup.app import SetupService
from codex_setup.core import paths
from codex_setup.diagnostics.api_test import ApiTestReport, Outcome, Problem, StepResult
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.secrets import SecretStore

KEY = "sk-test-SECRET-1234567890"


def _install() -> CodexInstall:
    return CodexInstall(None, None, False, False, None, None, "n/a")


@pytest.fixture
def svc(monkeypatch: pytest.MonkeyPatch) -> SetupService:
    s = SetupService(secret_store=SecretStore(backend="session"))
    s._platform = PlatformInfo("macos", "25", "arm64")
    s._install = _install()
    monkeypatch.setattr(cli, "make_service", lambda: s)
    cli._SEEN_SECRETS.clear()
    return s


def _cfg() -> Path:
    return paths.config_path()


def _stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("codex-setup ")


def test_no_key_option():
    assert cli.main(["setup", "--key", KEY]) == 2


def test_status_missing(svc, capsys):
    assert cli.main(["--lang", "en", "status"]) == 0
    assert "missing" in capsys.readouterr().out


def test_no_args_not_tty_prints_hint(svc, capsys, monkeypatch):
    _stdin(monkeypatch, "")
    assert cli.main(["--lang", "en", "--tui"]) == 0
    out = capsys.readouterr().out
    assert "codex-setup --help" in out


def test_setup_writes_config_keeps_settings(svc, capsys, monkeypatch):
    _cfg().parent.mkdir(parents=True)
    _cfg().write_text('approval_policy = "never"\n\n[tui]\nnotifications = true\n', encoding="utf-8")
    _stdin(monkeypatch, KEY + "\n")
    assert cli.main(["setup", "--yes", "--key-stdin"]) == 0
    cap = capsys.readouterr()
    data = tomllib.loads(_cfg().read_text(encoding="utf-8"))
    assert data["model_provider"] == "lunovant"
    assert data["model"] == "gpt-6.1-sol"
    assert data["model_providers"]["lunovant"] == {
        "name": "Lunovant",
        "base_url": "https://api.lunovant.tech/v1",
        "env_key": "LUNOVANT_API_KEY",
        "wire_api": "responses",
    }
    assert data["approval_policy"] == "never" and data["tui"] == {"notifications": True}
    state = (paths.app_state_dir() / "state.json").read_text(encoding="utf-8")
    for blob in (_cfg().read_text(encoding="utf-8"), state, cap.out, cap.err):
        assert KEY not in blob
    assert svc.secret_store().get("LUNOVANT_API_KEY") == KEY
    st = json.loads(state)
    (own,) = st["configs"].values()
    assert own["managed_provider_ids"] == ["lunovant"]
    assert own["original_top_level"] == {"model": None, "model_provider": None}


def test_setup_dry_run(svc, capsys, monkeypatch):
    _stdin(monkeypatch, KEY + "\n")
    assert cli.main(["setup", "--dry-run", "--key-stdin"]) == 0
    out = capsys.readouterr().out
    assert "lunovant" in out and "+" in out
    assert not _cfg().exists()
    assert not (paths.app_state_dir() / "state.json").exists()
    assert svc.secret_store().get("LUNOVANT_API_KEY") is None


def _setup(monkeypatch):
    _stdin(monkeypatch, KEY + "\n")
    assert cli.main(["setup", "--yes", "--key-stdin"]) == 0


def test_model_change_and_invalid(svc, capsys, monkeypatch):
    _setup(monkeypatch)
    assert cli.main(["model", "gpt-6.1-terra", "--yes"]) == 0
    assert tomllib.loads(_cfg().read_text())["model"] == "gpt-6.1-terra"
    assert cli.main(["model", "bad name", "--yes"]) == 1
    assert tomllib.loads(_cfg().read_text())["model"] == "gpt-6.1-terra"


def test_sandbox_windows_and_macos(svc, capsys, monkeypatch):
    assert cli.main(["sandbox", "unelevated", "--yes"]) == 0
    assert not _cfg().exists()
    assert "not applicable" in capsys.readouterr().out.lower()
    svc._platform = PlatformInfo("windows", "11", "AMD64")
    assert cli.main(["sandbox", "unelevated", "--yes"]) == 0
    assert tomllib.loads(_cfg().read_text())["windows"]["sandbox"] == "unelevated"
    assert cli.main(["sandbox", "remove", "--yes"]) == 0
    assert "windows" not in tomllib.loads(_cfg().read_text())


def test_backup_list_and_restore(svc, capsys, monkeypatch):
    _cfg().parent.mkdir(parents=True)
    original = 'model = "gpt-5"\n'
    _cfg().write_text(original, encoding="utf-8")
    _setup(monkeypatch)
    capsys.readouterr()
    assert cli.main(["backup", "list"]) == 0
    first = capsys.readouterr().out.strip().splitlines()[-1].split()[0]
    assert first.startswith("config-")
    assert cli.main(["backup", "original", "--yes"]) == 0
    assert _cfg().read_text() == original
    assert cli.main(["backup", "restore", first, "--yes"]) == 0
    assert cli.main(["backup", "restore", "nope", "--yes"]) == 1


def test_uninstall_restores_original(svc, monkeypatch):
    _cfg().parent.mkdir(parents=True)
    _cfg().write_text(
        'model = "gpt-5"\nmodel_provider = "other"\n\n[model_providers.other]\nname = "O"\n'
        'base_url = "https://o.example/v1"\nenv_key = "O_KEY"\nwire_api = "responses"\n',
        encoding="utf-8",
    )
    _setup(monkeypatch)
    assert tomllib.loads(_cfg().read_text())["model_provider"] == "lunovant"
    backups_before = len(svc.backup_list())
    assert cli.main(["uninstall", "--yes"]) == 0
    data = tomllib.loads(_cfg().read_text())
    assert data["model"] == "gpt-5" and data["model_provider"] == "other"
    assert list(data["model_providers"]) == ["other"]
    assert len(svc.backup_list()) >= backups_before


def test_profile_add_use(svc, monkeypatch):
    _setup(monkeypatch)
    assert cli.main(["profile", "add", "acme", "--base-url", "https://acme.example/v1",
                     "--env-key", "ACME_KEY", "--model", "acme-1"]) == 0
    assert cli.main(["profile", "use", "acme", "--yes"]) == 0
    data = tomllib.loads(_cfg().read_text())
    assert data["model_provider"] == "acme" and data["model"] == "acme-1"
    assert set(data["model_providers"]) == {"lunovant", "acme"}
    assert cli.main(["profile", "use", "lunovant", "--yes"]) == 0
    data = tomllib.loads(_cfg().read_text())
    assert data["model_provider"] == "lunovant"
    assert set(data["model_providers"]) == {"lunovant", "acme"}
    assert cli.main(["profile", "add", "openai", "--model", "gpt-5"]) == 0
    assert cli.main(["profile", "use", "openai", "--yes"]) == 0
    data = tomllib.loads(_cfg().read_text())
    assert data["model_provider"] == "openai" and "openai" not in data["model_providers"]
    assert cli.main(["profile", "add", "ollama", "--base-url", "http://x", "--env-key", "K"]) == 1


def test_test_prints_fail_when_only_models_works(svc, capsys, monkeypatch):
    _setup(monkeypatch)
    report = ApiTestReport(
        steps=[
            StepResult("connect", Outcome.OK, None, "reachable"),
            StepResult("models", Outcome.OK, None, "ok"),
            StepResult("responses", Outcome.FAIL, Problem.RESPONSES_UNSUPPORTED, "404"),
        ],
        overall=Outcome.FAIL,
    )
    monkeypatch.setattr("codex_setup.app.run_api_test", lambda *a, **k: report)
    capsys.readouterr()
    assert cli.main(["test"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert svc.load_state().last_test["overall"] == "fail"


def test_diagnose_text(svc, capsys):
    assert cli.main(["--lang", "en", "diagnose", "--text", "Couldn't check Windows setup"]) == 0
    assert "unelevated" in capsys.readouterr().out


def test_error_is_redacted_exit_1(svc, capsys):
    assert cli.main(["--lang", "en", "model", "x y", "--yes"]) == 1
    assert capsys.readouterr().err.startswith("Error:")
