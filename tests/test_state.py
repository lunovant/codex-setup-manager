from __future__ import annotations

import json
from pathlib import Path

from codex_setup.core import paths
from codex_setup.core.state import AppState, Profile, load_state, save_state
from codex_setup.providers.catalog import DEFAULT_MODEL, LUNOVANT, LUNOVANT_MODELS


def test_missing_returns_default(isolated_env) -> None:
    assert load_state(isolated_env) == AppState()


def test_round_trip(isolated_env) -> None:
    state = AppState(
        profiles={"lunovant": Profile("lunovant", LUNOVANT, DEFAULT_MODEL, list(LUNOVANT_MODELS))},
        active_profile="lunovant",
        managed_provider_ids=["lunovant"],
        original_top_level={"model": "gpt-5", "model_provider": None},
        original_snapshot="",
        secret_backend="keyring",
        last_test={"when": "2026-11-09T00:00:00", "overall": "ok", "model": DEFAULT_MODEL},
    )
    save_state(state, isolated_env)
    assert load_state(isolated_env) == state


def test_no_secrets_keys(isolated_env) -> None:
    save_state(AppState(secret_backend="session"), isolated_env)
    raw = (paths.app_state_dir(isolated_env) / "state.json").read_text()
    assert "api_key" not in raw and "secret\"" not in raw
    assert json.loads(raw)["secret_backend"] == "session"


def test_corrupt_renamed(isolated_env) -> None:
    path = paths.app_state_dir(isolated_env) / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_state(isolated_env) == AppState()
    assert not path.exists()
    assert (path.parent / "state.json.bad").read_text() == "{not json"


def test_wrong_shape_treated_as_corrupt(isolated_env) -> None:
    path = paths.app_state_dir(isolated_env) / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2]", encoding="utf-8")
    assert load_state(isolated_env) == AppState()
    assert Path(str(path) + ".bad").exists()
