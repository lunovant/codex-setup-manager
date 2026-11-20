"""v0.3.1: coexist with a personal ChatGPT login (modes, profile file, legacy cleanup)."""

from __future__ import annotations

import io
import json
import tomllib
from pathlib import Path

import pytest

from codex_setup import main as cli
from codex_setup.app import PROFILE_HEADER, SetupService, format_key_info
from codex_setup.core import paths
from codex_setup.core.errors import CodexSetupError
from codex_setup.core.state import load_state
from codex_setup.diagnostics import model_probe
from codex_setup.gui.api import GuiApi
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.secrets import SecretStore

KEY = "sk-lunovant-SECRET-1234567890"
TOKEN = "eyJ-SUPER-SECRET-ACCESS-TOKEN"
USAGE = {"valid": True, "expired": False, "plan": None, "remaining": 12.3456,
         "expires_at": None, "days_left": None}


@pytest.fixture
def svc(monkeypatch) -> SetupService:
    s = SetupService(secret_store=SecretStore(backend="session"))
    s._platform = PlatformInfo("macos", "25", "arm64")
    s._install = CodexInstall(None, None, False, False, None, None, "n/a")
    monkeypatch.setattr(model_probe, "check_key", lambda *a, **k: dict(USAGE))
    monkeypatch.setattr(model_probe, "fetch_models",
                        lambda *a, **k: ["gpt-6.1-sol", "gpt-image-2", "my-image-x", "gpt-6-luna"])
    monkeypatch.setattr(
        model_probe, "probe_models",
        lambda url, key, models, **k: [
            {"model": m, "ok": True, "latency_ms": 5, "status_code": 200, "error": None}
            for m in models])
    return s


def _cfg() -> Path:
    return paths.config_path()


def _top() -> dict:
    d = tomllib.loads(_cfg().read_text())
    return {k: d.get(k) for k in ("model", "model_provider")}


def _profile() -> Path:
    return paths.profile_config_path("lunovant")


def _auth(mode: str = "chatgpt") -> None:
    _cfg().parent.mkdir(parents=True, exist_ok=True)
    (_cfg().parent / "auth.json").write_text(
        json.dumps({"auth_mode": mode, "tokens": {"access_token": TOKEN}}))


def _write_cfg(text: str) -> None:
    _cfg().parent.mkdir(parents=True, exist_ok=True)
    _cfg().write_text(text)


def test_profile_file_written_updated_removed(svc):
    assert svc.one_click_setup(KEY).ok
    text = _profile().read_text()
    assert text.startswith(PROFILE_HEADER)
    data = tomllib.loads(text)
    assert data == {"model_provider": "lunovant", "model": "gpt-6.1-sol"}
    assert KEY not in text
    svc.change_model("gpt-6-luna")
    assert tomllib.loads(_profile().read_text())["model"] == "gpt-6-luna"
    svc.uninstall()
    assert not _profile().exists()


def test_uninstall_keeps_foreign_profile_file(svc):
    svc.one_click_setup(KEY)
    _profile().write_text("model = 'mine'\n")
    svc.uninstall()
    assert _profile().read_text() == "model = 'mine'\n"


def test_foreign_profile_file_is_backed_up(svc):
    _profile().parent.mkdir(parents=True)
    _profile().write_text("model = 'mine'\n")
    svc.one_click_setup(KEY)
    assert _profile().read_text().startswith(PROFILE_HEADER)
    # profile backups never appear in the config backup list (restoring one would clobber config)
    assert not any("model = 'mine'" in b.path.read_text() for b in svc.backup_list())
    saved = list((paths.app_state_dir() / "profile-backups").glob("lunovant.config.toml.*.bak"))
    assert [f.read_text() for f in saved] == ["model = 'mine'\n"]


def test_restore_after_profile_backup_keeps_config(svc):
    _profile().parent.mkdir(parents=True)
    _profile().write_text("model = 'mine'\n")
    svc.one_click_setup(KEY)
    cfg = _cfg().read_text()
    for b in svc.backup_list():
        assert b.source == str(_cfg())
    assert _cfg().read_text() == cfg


def test_profile_backup_failure_aborts_before_any_write(svc, monkeypatch):
    _write_cfg('model = "m"\n')
    _profile().write_text("model = 'mine'\n")
    before = _cfg().read_text()

    paths.app_state_dir().mkdir(parents=True, exist_ok=True)
    (paths.app_state_dir() / "profile-backups").write_text("blocked")  # mkdir will fail
    with pytest.raises(CodexSetupError):
        svc.one_click_setup(KEY)
    assert _cfg().read_text() == before and _profile().read_text() == "model = 'mine'\n"
    assert not (paths.app_state_dir() / "state.json").exists()


def test_profile_update_is_backed_up(svc):
    svc.one_click_setup(KEY)
    svc.change_model("gpt-6-luna")
    saved = list((paths.app_state_dir() / "profile-backups").glob("*.bak"))
    assert len(saved) == 1 and "gpt-6.1-sol" in saved[0].read_text()


def test_personal_rerun_and_repeat_keep_user_edits(svc):
    _auth()
    _write_cfg('model = "a"\nmodel_provider = "openai"\n')
    svc.one_click_setup(KEY, mode="personal")
    _cfg().write_text(_cfg().read_text().replace('model = "a"', 'model = "b"'))
    svc.one_click_setup(KEY, mode="personal")
    assert _top() == {"model": "b", "model_provider": "openai"}
    svc.set_mode("personal")
    assert _top() == {"model": "b", "model_provider": "openai"}
    svc.set_mode("lunovant")
    svc.set_mode("personal")
    assert _top() == {"model": "b", "model_provider": "openai"}


def test_set_mode_cleans_legacy_profile_key(svc):
    svc.one_click_setup(KEY)
    _cfg().write_text('profile = "old"\n' + _cfg().read_text())
    res = svc.set_mode("personal")
    assert "profile" not in tomllib.loads(_cfg().read_text())
    assert ("legacy_profile_removed", {"value": "old"}) in res.notes
    assert svc.ownership().legacy_profile["value"] == "old"
    un = svc.uninstall()
    assert "profile" not in tomllib.loads(_cfg().read_text()) if _cfg().exists() else True
    assert any(k == "legacy_profile_removed" for k, _ in un.notes)


def test_gui_filters_stale_image_models(svc):
    gui = GuiApi(svc, lang="en")
    svc.one_click_setup(KEY)
    state = load_state()
    state.one_click["models"] = ["gpt-6.1-sol", "gpt-image-1", "codex-auto-review"]
    state.one_click["results"] = [
        {"model": m, "ok": True, "latency_ms": 1, "status_code": 200, "error": None}
        for m in state.one_click["models"]]
    from codex_setup.core.state import save_state
    save_state(state)
    last = gui.one_click_last()
    assert last["models"] == ["gpt-6.1-sol"]
    assert [r["model"] for r in last["results"]] == ["gpt-6.1-sol"]
    assert not gui.reprobe_model("gpt-image-1")["ok"]
    assert not gui.reprobe_model("codex-auto-review")["ok"]


def test_quick_setup_writes_profile(svc):
    svc.quick_setup(None, "gpt-6.1-sol", None, "session")
    assert tomllib.loads(_profile().read_text())["model_provider"] == "lunovant"
    svc.uninstall()
    assert not _profile().exists()


def test_legacy_profile_removed(svc):
    _write_cfg('profile = "old"\nmodel = "m"\n\n[profiles.old]\nmodel = "x"\n')
    res = svc.one_click_setup(KEY)
    assert res.ok and res.legacy_profile == "old" and res.legacy_profile_tables == ["old"]
    assert "profile" in res.message and "[profiles.*]" in res.message
    doc = tomllib.loads(_cfg().read_text())
    assert "profile" not in doc and doc["profiles"]["old"]["model"] == "x"
    svc.uninstall()
    assert "profile" not in tomllib.loads(_cfg().read_text())  # never restored


def test_legacy_profile_removed_quick_setup(svc):
    _write_cfg('profile = "old"\n')
    res = svc.quick_setup(None, "gpt-6.1-sol", None, "session")
    assert "profile" not in tomllib.loads(_cfg().read_text())
    assert ("legacy_profile_removed", {"value": "old"}) in res.notes


@pytest.mark.parametrize("original", ['model = "gpt-5"\nmodel_provider = "openai"\n', "", 'model = "only-model"\n'])
def test_mode_round_trip(svc, original):
    if original:
        _write_cfg(original)
    before = _top() if original else {"model": None, "model_provider": None}
    svc.one_click_setup(KEY)
    assert svc.current_mode() == "lunovant" and _top()["model_provider"] == "lunovant"
    svc.set_mode("personal")
    assert svc.current_mode() == "personal"
    assert _top() == before
    assert "lunovant" in tomllib.loads(_cfg().read_text())["model_providers"]
    assert _profile().exists()
    svc.set_mode("lunovant")
    assert _top() == {"model": "gpt-6.1-sol", "model_provider": "lunovant"}
    svc.set_mode("personal")
    assert _top() == before
    svc.uninstall()
    assert _top() == before


def test_mode_picks_up_user_changes_in_personal_mode(svc):
    _write_cfg('model = "a"\nmodel_provider = "openai"\n')
    svc.one_click_setup(KEY)
    svc.set_mode("personal")
    _cfg().write_text(_cfg().read_text().replace('model = "a"', 'model = "b"'))
    svc.set_mode("lunovant")
    svc.set_mode("personal")
    assert _top() == {"model": "b", "model_provider": "openai"}


def test_mode_round_trip_keeps_model_picked_in_codex(svc):
    _write_cfg('model = "a"\nmodel_provider = "openai"\n')
    svc.one_click_setup(KEY)
    # the Codex picker edits config.toml directly, bypassing change_model
    _cfg().write_text(_cfg().read_text().replace('model = "gpt-6.1-sol"', 'model = "gpt-6-luna"'))
    svc.set_mode("personal")
    assert _top() == {"model": "a", "model_provider": "openai"}
    assert tomllib.loads(_profile().read_text())["model"] == "gpt-6-luna"
    svc.set_mode("lunovant")
    assert _top() == {"model": "gpt-6-luna", "model_provider": "lunovant"}


def test_set_mode_requires_setup_and_valid_mode(svc):
    with pytest.raises(CodexSetupError):
        svc.set_mode("personal")
    with pytest.raises(CodexSetupError):
        svc.set_mode("bogus")


def test_one_click_personal_leaves_top_level(svc):
    _auth()
    _write_cfg('model = "gpt-5"\nmodel_provider = "openai"\n')
    res = svc.one_click_setup(KEY, mode="personal")
    assert res.ok and res.mode == "personal"
    assert _top() == {"model": "gpt-5", "model_provider": "openai"}
    assert "lunovant" in tomllib.loads(_cfg().read_text())["model_providers"]
    assert tomllib.loads(_profile().read_text())["model_provider"] == "lunovant"
    svc.change_model("gpt-6-luna")  # personal: only the profile moves
    assert _top()["model"] == "gpt-5"
    assert tomllib.loads(_profile().read_text())["model"] == "gpt-6-luna"
    assert svc.current_mode() == "personal"


def test_chatgpt_detection_never_leaks_token(svc):
    assert not svc.chatgpt_login_present()
    _auth("chatgpt")
    assert svc.chatgpt_login_present()
    _auth("apikey")
    assert svc.chatgpt_login_present()  # tokens present
    (_cfg().parent / "auth.json").write_text(json.dumps({"auth_mode": "apikey"}))
    assert not svc.chatgpt_login_present()
    (_cfg().parent / "auth.json").write_text("not json")
    assert not svc.chatgpt_login_present()
    _auth()
    svc.one_click_setup(KEY, mode="personal")
    blob = (paths.app_state_dir() / "state.json").read_text() + _cfg().read_text() + _profile().read_text()
    assert TOKEN not in blob
    assert "requires_openai_auth" not in blob


def test_image_models_filtered(svc):
    res = svc.one_click_setup(KEY)
    names = [r["model"] for r in res.models]
    assert names == ["gpt-6.1-sol", "gpt-6-luna"]
    assert svc.available_models() == names
    assert model_probe.is_excluded_model("gpt-image-1") and model_probe.is_excluded_model("codex-auto-review")
    assert model_probe.parse_models({"data": [{"id": "gpt-image-2"}, {"id": "a"}]}) == ["a"]


def test_key_info_formatting():
    assert format_key_info({"plan": None, "remaining": 12.3456, "expires_at": None}) == {
        "plan": None, "remaining": "12.35", "expires": None}
    assert format_key_info({"plan": "Pro", "remaining": 3, "expires_at": "2099"})["remaining"] == "3"
    assert cli.format_key_line({"plan": None, "remaining": 12.3456}).startswith("12.35💎")


def _stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_cli_setup_keep_personal_and_mode(svc, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    cli._SEEN_SECRETS.clear()
    _write_cfg('model = "gpt-5"\nmodel_provider = "openai"\n')
    _stdin(monkeypatch, KEY + "\n")
    assert cli.main(["--lang", "en", "setup", "--auto", "--keep-personal"]) == 0
    out = capsys.readouterr().out
    assert "no expiry" in out and "12.35💎" in out and "None" not in out and "?" not in out
    assert _top() == {"model": "gpt-5", "model_provider": "openai"}
    assert cli.main(["--lang", "en", "mode"]) == 0
    assert "personal" in capsys.readouterr().out
    assert cli.main(["--lang", "en", "--yes", "mode", "lunovant"]) == 0
    assert _top()["model_provider"] == "lunovant"
    assert cli.main(["--lang", "en", "mode"]) == 0
    assert "lunovant" in capsys.readouterr().out
    assert cli.main(["--lang", "vi", "--yes", "mode", "personal"]) == 0
    assert _top() == {"model": "gpt-5", "model_provider": "openai"}


def test_cli_mode_without_setup_fails(svc, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    assert cli.main(["--lang", "en", "--yes", "mode", "personal"]) != 0


def test_gui_mode_switch_and_detection(svc):
    gui = GuiApi(svc, lang="en")
    st = gui.status()
    assert st["chatgpt_login"] is False and st["lunovant_installed"] is False
    _auth()
    assert gui.status()["chatgpt_login"] is True
    res = svc.one_click_setup(KEY)
    assert res.ok
    st = gui.status()
    assert st["mode"] == "lunovant" and st["lunovant_installed"] is True
    out = gui.set_mode("personal")
    assert out["ok"] and out["mode"] == "personal"
    assert gui.status()["mode"] == "personal"
    assert gui.one_click_last()["has_last"] is True  # still shown in personal mode
    assert gui.set_mode("lunovant")["mode"] == "lunovant"
    assert not gui.set_mode("bogus")["ok"]
    json.dumps(st)


def test_gui_personal_requires_login(svc):
    gui = GuiApi(svc, lang="en")
    svc.one_click_setup(KEY)
    res = gui.set_mode("personal")
    assert not res["ok"]
    assert gui.status()["mode"] == "lunovant"


def test_gui_one_click_start_ignores_personal_without_login(svc):
    import time

    gui = GuiApi(svc, lang="en")
    assert gui.one_click_start(KEY, "personal")["ok"]
    for _ in range(100):
        if not gui.one_click_poll()["running"]:
            break
        time.sleep(0.05)
    assert gui.one_click_poll()["result"]["mode"] == "lunovant"
    assert gui.one_click_start(KEY, "weird")["ok"] is False


def test_state_has_no_token(svc):
    _auth()
    svc.one_click_setup(KEY, mode="personal")
    assert TOKEN not in json.dumps(load_state().to_dict())
