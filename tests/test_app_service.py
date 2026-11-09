from __future__ import annotations

import tomllib

import pytest

from codex_setup.app import SetupService
from codex_setup.core import config_store, paths
from codex_setup.core.errors import ConfigWriteError, ReservedProviderError, ValidationError
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.providers.catalog import LUNOVANT_MODELS
from codex_setup.security.secrets import SecretStore


@pytest.fixture
def svc() -> SetupService:
    s = SetupService(secret_store=SecretStore(backend="session"))
    s._platform = PlatformInfo("macos", "25", "arm64")
    s._install = CodexInstall(None, None, False, False, None, None, "n/a")
    return s


def test_quick_setup_flow(svc):
    res = svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    assert res.changed and "lunovant" in res.diff
    st = svc.load_state()
    assert st.managed_provider_ids == ["lunovant"]
    assert st.original_snapshot == "" and st.active_profile == "lunovant"
    assert svc.secret_store().get("LUNOVANT_API_KEY") == "k-1234567890"
    # second run does not re-record originals or duplicate the managed id
    svc.quick_setup(None, "gpt-6-luna", None, "session")
    st = svc.load_state()
    assert st.managed_provider_ids == ["lunovant"]
    assert st.original_top_level == {"model": None, "model_provider": None}


def test_preexisting_lunovant_not_managed(svc):
    cfg = paths.config_path()
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[model_providers.lunovant]\nname = "L"\nbase_url = "https://x/v1"\n'
                   'env_key = "LUNOVANT_API_KEY"\nwire_api = "responses"\n', encoding="utf-8")
    svc.quick_setup(None, "gpt-6.1-sol", None, "session")
    assert svc.load_state().managed_provider_ids == []


def test_custom_url_and_models(svc):
    svc.quick_setup("https://proxy.example.com/v1/", "my-model", None, "session")
    data = tomllib.loads(paths.config_path().read_text())
    assert data["model_providers"]["lunovant"]["base_url"] == "https://proxy.example.com/v1"
    assert svc.custom_models() == ["my-model"]
    assert svc.available_models()[: len(LUNOVANT_MODELS)] == list(LUNOVANT_MODELS)
    svc.add_custom_model("m2")
    svc.edit_custom_model("m2", "m3")
    svc.remove_custom_model("m3")
    assert svc.custom_models() == ["my-model"]


def test_dry_run_writes_nothing(svc):
    res = svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session", dry_run=True)
    assert res.dry_run and res.diff
    assert not paths.config_path().exists()
    assert not (paths.app_state_dir() / "state.json").exists()


def test_write_failure_surfaces_and_rolls_back(svc, monkeypatch):
    cfg = paths.config_path()
    cfg.parent.mkdir(parents=True)
    original = 'model = "gpt-5"\n'
    cfg.write_text(original, encoding="utf-8")
    real = config_store.atomic_write_text
    calls = {"n": 0}

    def flaky(path, text):
        calls["n"] += 1
        if calls["n"] == 1:
            real(path, text + "\n[broken\n")  # corrupt content lands on disk
            return
        real(path, text)

    monkeypatch.setattr(config_store, "atomic_write_text", flaky)
    with pytest.raises(ConfigWriteError):
        svc.change_model("gpt-6-luna")
    assert cfg.read_text() == original


def test_reserved_and_validation(svc):
    with pytest.raises(ReservedProviderError):
        svc.add_profile("ollama", "http://x", "K")
    with pytest.raises(ValidationError):
        svc.quick_setup(None, "bad model", None, "session")
    with pytest.raises(ValidationError):
        svc.quick_setup(None, "gpt-6.1-sol", "line1\nline2", "session")


def test_env_install_requires_consent(svc):
    svc.quick_setup(None, "gpt-6.1-sol", "k-1234567890", "session")
    with pytest.raises(Exception):
        svc.env_install(False)


def test_sandbox_not_applicable_on_macos(svc):
    assert svc.sandbox("unelevated") is None
