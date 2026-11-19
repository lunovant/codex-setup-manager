from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

import httpx
import pytest
import tomlkit

from codex_setup.app import SetupService
from codex_setup.core import model_catalog as mc
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.secrets import SecretStore

REAL_FIND = mc.find_codex_binaries  # conftest replaces the module attribute per test

KEY = "sk-lunovant-SECRET-1234567890"
USAGE_OK = {"isValid": True, "status": "active", "expires_at": "2099-01-01T00:00:00Z",
            "remaining": 12.5, "planName": "Pro"}
SOLD_IDS = ["gpt-6.1-sol", "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6-luna",
            "codex-auto-review", "gpt-image-2"]


def entry(slug: str, display: str, priority: int, visibility: str = "list") -> dict:
    return {
        "slug": slug, "display_name": display, "priority": priority, "visibility": visibility,
        "description": f"{display} description",
        "base_instructions": f"You are {display} ({slug}).",
        "context_window": 272000,
        "supported_reasoning_levels": [{"effort": "low", "description": f"{slug} low"}],
        "model_messages": {"a": [f"model {slug}"]},
    }


def bundled() -> dict:
    return {"models": [
        entry("gpt-6-astra", "GPT-6-Astra", 2),
        entry("gpt-6.1-sol", "GPT-6.1-Sol", 1),
        entry("gpt-6-sol", "GPT-6-Sol", 3),
        entry("gpt-6-luna", "GPT-6-Luna", 4),
        entry("gpt-5.6-sol", "GPT-5.6-Sol", 5),
        entry("gpt-5.6-terra", "GPT-5.6-Terra", 8),
        entry("gpt-5.5", "GPT-5.5", 13),
        entry("gpt-daybreak-blue-latest", "Daybreak Blue", 11, "hide"),
        entry("codex-auto-review", "Codex Auto Review", 43, "hide"),
    ]}


class FakeCodex:
    """Fake binary runner: per-path version, bundled catalog, validation outcome."""

    def __init__(self, versions: dict[str, str], failing: set[str] = frozenset(),
                 catalogs: dict[str, dict] | None = None) -> None:
        self.versions, self.failing, self.catalogs = versions, set(failing), catalogs or {}
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, argv, env, timeout):
        argv = list(argv)
        self.calls.append((argv, dict(env)))
        path = argv[0]
        if argv[1:] == ["--version"]:
            return 0, f"codex-cli {self.versions[path]}\n", ""
        if argv[1:] == ["debug", "models", "--bundled"]:
            return 0, json.dumps(self.catalogs.get(path, bundled())), ""
        assert argv[1:4] == ["debug", "models", "-c"], argv
        override = argv[4]
        assert override.startswith("model_catalog_json=")
        file = Path(tomllib.loads(override)["model_catalog_json"])
        if path in self.failing:
            return 1, "", "invalid catalog"
        return 0, file.read_text(encoding="utf-8"), ""


def binaries(fake: FakeCodex) -> list[mc.CodexBinary]:
    return [mc.CodexBinary(p, v) for p, v in fake.versions.items()]


# -- version parsing / finding -------------------------------------------------
def test_parse_version_and_ordering() -> None:
    assert mc.parse_version("codex-cli 0.169.0-alpha.11.1") == "0.169.0-alpha.11.1"
    assert mc.parse_version("codex-cli 0.162.1\n") == "0.162.1"
    assert mc.parse_version("nothing") is None
    k = mc.version_key
    assert k("0.169.0-alpha.11.1") > k("0.169.0-alpha.2") > k("0.165.0-alpha.1")
    assert k("0.169.0") > k("0.169.0-alpha.11.1")
    assert k("0.162.1") < k("0.165.0-alpha.1")


def test_find_binaries_sources_and_newest_extension(tmp_path: Path) -> None:
    home = tmp_path / "h"
    old = home / ".vscode" / "extensions" / "openai.chatgpt-0.168.0-darwin-arm64" / "bin" / "macos-aarch64"
    new = home / ".vscode" / "extensions" / "openai.chatgpt-0.169.0-alpha.11-darwin-arm64" / "bin" / "macos-aarch64"
    cur = home / ".cursor" / "extensions" / "openai.chatgpt-0.169.0-alpha.11-darwin-arm64" / "bin" / "macos-aarch64"
    app = tmp_path / "Applications" / "ChatGPT.app" / "Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS"
    path_bin = tmp_path / "bin"
    for d in (old, new, cur, app, path_bin):
        d.mkdir(parents=True)
        (d / "codex").write_text("x")
    versions = {
        str(path_bin / "codex"): "0.162.1", str(app / "codex"): "0.165.0-alpha.1",
        str(new / "codex"): "0.169.0-alpha.11.1", str(cur / "codex"): "0.169.0-alpha.11.1",
        str(old / "codex"): "0.168.0",
    }
    fake = FakeCodex(versions)
    found = REAL_FIND(
        env={}, system="macos", home=home, which=lambda n: str(path_bin / "codex"),
        runner=fake, app_roots=[tmp_path / "Applications"],
    )
    paths = {b.path for b in found}
    assert paths == {str(path_bin / "codex"), str(app / "codex"), str(new / "codex"), str(cur / "codex")}
    assert all(c[0][1:] == ["--version"] for c in fake.calls)


def test_find_skips_broken_binary(tmp_path: Path) -> None:
    def runner(argv, env, timeout):
        raise OSError("exec format error")

    assert REAL_FIND(
        env={}, system="linux", home=tmp_path, which=lambda n: "/x/codex", runner=runner) == []


# -- clone logic -----------------------------------------------------------------
def test_build_clones_hides_and_keeps_internal() -> None:
    sold = ["gpt-6.1-sol", "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6-luna"]
    cat, cloned, hidden = mc.build_catalog(bundled(), sold, "gpt-6.1-sol")
    by = {e["slug"]: e for e in cat["models"]}
    assert set(cloned) == {"gpt-6.2-sol", "gpt-6.2-astra"}
    sol, astra = by["gpt-6.2-sol"], by["gpt-6.2-astra"]
    assert sol["display_name"] == "GPT-6.2-Sol" and astra["display_name"] == "GPT-6.2-Astra"
    assert sol["visibility"] == astra["visibility"] == "list"
    # slug replaced in every string field (cloned from 6.1-sol / 6-astra)
    blob = json.dumps(sol)
    assert "gpt-6.1-sol" not in blob and "GPT-6.1-Sol" not in blob and "gpt-6.2-sol" in blob
    assert "gpt-6-astra" not in json.dumps(astra) and by["gpt-6.2-astra"]["base_instructions"] == \
        "You are GPT-6.2-Astra (gpt-6.2-astra)."
    assert sol["context_window"] == 272000
    # unsold listed -> hide; hidden internal untouched
    for slug in ("gpt-6-astra", "gpt-6-sol", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.5"):
        assert by[slug]["visibility"] == "hide" and slug in hidden
    assert by["codex-auto-review"] == bundled()["models"][-1]
    assert by["gpt-daybreak-blue-latest"]["visibility"] == "hide"
    assert by["gpt-6.1-sol"]["visibility"] == "list" and by["gpt-6-luna"]["visibility"] == "list"
    # newer versions sort first among the listed ones
    listed = sorted((e for e in cat["models"] if e["visibility"] == "list"),
                    key=lambda e: e["priority"])
    assert [e["slug"] for e in listed][:2] == ["gpt-6.2-sol", "gpt-6.2-astra"]
    assert [e["slug"] for e in listed][2] == "gpt-6.1-sol"
    assert len({e["priority"] for e in listed}) == len(listed)


def test_template_fallback_default_then_first_listed() -> None:
    base = {"models": [entry("gpt-5.5", "GPT-5.5", 1), entry("gpt-6.1-sol", "GPT-6.1-Sol", 2)]}
    cat, cloned, _ = mc.build_catalog(base, ["gpt-7-zeta"], "gpt-6.1-sol")
    new = next(e for e in cat["models"] if e["slug"] == "gpt-7-zeta")
    assert new["display_name"] == "GPT-7-Zeta" and "gpt-6.1-sol" not in json.dumps(new)
    cat, _, _ = mc.build_catalog(base, ["gpt-7-zeta"], None)
    new = next(e for e in cat["models"] if e["slug"] == "gpt-7-zeta")
    assert "gpt-5.5" not in json.dumps(new)
    with pytest.raises(mc.CatalogError):
        mc.build_catalog({"models": []}, ["gpt-6.1-sol"])


# -- create_catalog ------------------------------------------------------------------
def test_highest_version_is_base(tmp_path: Path) -> None:
    low = {"models": [entry("gpt-6.1-sol", "GPT-6.1-Sol", 1)]}
    fake = FakeCodex({"/a/codex": "0.162.1", "/b/codex": "0.169.0-alpha.11.1"},
                     catalogs={"/a/codex": low})
    res = mc.create_catalog(tmp_path, ["gpt-6.1-sol", "gpt-6.2-sol"], default_model="gpt-6.1-sol",
                            env={"PATH": "x"}, binaries=binaries(fake), runner=fake)
    assert res.ok and res.path == tmp_path / mc.CATALOG_FILE
    assert not res.path.exists() and res.candidate.is_file()  # nothing live before publish
    mc.publish(res)
    bundled_calls = [c for c in fake.calls if c[0][1:] == ["debug", "models", "--bundled"]]
    assert [c[0][0] for c in bundled_calls] == ["/b/codex"]
    assert all(c[1]["CODEX_HOME"] == str(tmp_path) for c in fake.calls)
    if os.name == "posix":
        assert (res.path.stat().st_mode & 0o777) == 0o600
    assert not list(tmp_path.glob(".*.tmp"))


def test_validation_failure_on_any_binary_removes_file(tmp_path: Path) -> None:
    fake = FakeCodex({"/a/codex": "0.162.1", "/b/codex": "0.169.0"}, failing={"/a/codex"})
    res = mc.create_catalog(tmp_path, ["gpt-6.1-sol", "gpt-6.2-sol"], default_model=None,
                            env={}, binaries=binaries(fake), runner=fake)
    assert not res.ok and res.note == ("catalog_failed", {"version": "0.162.1"})
    assert not (tmp_path / mc.CATALOG_FILE).exists()
    assert not list(tmp_path.glob("*lunovant-models*"))  # candidate removed too


def test_validation_requires_all_sold_models(tmp_path: Path) -> None:
    class Drops(FakeCodex):
        def __call__(self, argv, env, timeout):
            rc, out, err = super().__call__(argv, env, timeout)
            if argv[1:4] == ["debug", "models", "-c"]:
                data = json.loads(out)
                data["models"] = [m for m in data["models"] if m["slug"] != "gpt-6.2-sol"]
                out = json.dumps(data)
            return rc, out, err

    fake = Drops({"/a/codex": "0.169.0"})
    res = mc.create_catalog(tmp_path, ["gpt-6.2-sol"], default_model=None, env={},
                            binaries=binaries(fake), runner=fake)
    assert not res.ok and not (tmp_path / mc.CATALOG_FILE).exists()


def test_no_binary_skips_with_note(tmp_path: Path) -> None:
    res = mc.create_catalog(tmp_path, ["gpt-6.2-sol"], default_model=None, env={}, binaries=[])
    assert not res.ok and res.note == ("catalog_no_codex", {})


# -- service wiring ----------------------------------------------------------------
def make_client(models=SOLD_IDS):
    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/v1/usage":
            return httpx.Response(200, json=USAGE_OK)
        if p == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        if p == "/v1/responses":
            return httpx.Response(200, json={"object": "response", "output": []})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def fake(monkeypatch) -> FakeCodex:
    f = FakeCodex({"/a/codex": "0.162.1", "/b/codex": "0.169.0-alpha.11.1"})
    monkeypatch.setattr(mc, "find_codex_binaries", lambda **kw: binaries(f))
    return f


@pytest.fixture
def svc(fake) -> SetupService:
    s = SetupService(secret_store=SecretStore(backend="session"))
    s._platform = PlatformInfo("macos", "25", "arm64")
    s._install = CodexInstall(None, None, False, False, None, None, "n/a")
    s._catalog_runner = fake
    return s


def cfg(svc: SetupService) -> dict:
    return tomllib.loads(svc.config_path.read_text(encoding="utf-8"))


def profile(svc: SetupService) -> dict:
    return tomllib.loads(svc.profile_file.read_text(encoding="utf-8"))


def test_one_click_writes_catalog_and_wires_config(svc: SetupService) -> None:
    res = svc.one_click_setup(KEY, client=make_client())
    assert res.ok and res.catalog == {"ok": True, "listed": 4, "hidden": 5}
    path = str(svc.catalog_file)
    assert cfg(svc)["model_catalog_json"] == path
    assert profile(svc)["model_catalog_json"] == path
    data = json.loads(svc.catalog_file.read_text(encoding="utf-8"))
    listed = {m["slug"] for m in data["models"] if m["visibility"] == "list"}
    assert listed == {"gpt-6.1-sol", "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6-luna"}
    text = svc.catalog_file.read_text(encoding="utf-8")
    assert KEY not in text and "sk-" not in text and "token" not in text.lower()
    assert svc.ownership().model_catalog == path


def test_validation_failure_means_no_key_no_file_and_note(svc: SetupService, fake: FakeCodex) -> None:
    fake.failing.add("/a/codex")
    res = svc.one_click_setup(KEY, client=make_client())
    assert res.ok
    assert res.catalog["ok"] is False and res.catalog["code"] == "catalog_failed"
    assert res.catalog["params"] == {"version": "0.162.1"}
    assert "model_catalog_json" not in cfg(svc) and "model_catalog_json" not in profile(svc)
    assert not svc.catalog_file.exists()
    from codex_setup.ui import i18n
    i18n.set_lang("vi")
    try:
        assert i18n.catalog_text(res.catalog) == (
            "Không tạo được danh mục model cho Codex 0.162.1; "
            "danh sách chọn model có thể thiếu model mới.")
    finally:
        i18n.set_lang("en")


def test_no_binary_skips(svc: SetupService, monkeypatch) -> None:
    monkeypatch.setattr(mc, "find_codex_binaries", lambda **kw: [])
    res = svc.one_click_setup(KEY, client=make_client())
    assert res.ok and res.catalog["code"] == "catalog_no_codex"
    assert "model_catalog_json" not in cfg(svc)


def test_mode_round_trip(svc: SetupService) -> None:
    svc.one_click_setup(KEY, client=make_client())
    path = str(svc.catalog_file)
    svc.set_mode("personal")
    top = cfg(svc)
    assert "model_catalog_json" not in top and "model_provider" not in top and "model" not in top
    assert profile(svc)["model_catalog_json"] == path  # `codex -p lunovant` keeps it
    assert svc.catalog_file.exists()
    svc.set_mode("lunovant")
    assert cfg(svc)["model_catalog_json"] == path and cfg(svc)["model_provider"] == "lunovant"


def test_personal_setup_keeps_catalog_out_of_top_level(svc: SetupService) -> None:
    svc.one_click_setup(KEY, client=make_client(), mode="personal")
    assert "model_catalog_json" not in cfg(svc)
    assert profile(svc)["model_catalog_json"] == str(svc.catalog_file)


ORIGINALS = [
    'model = "mine"\n\n[model_providers.other]\nname = "x"\nbase_url = "http://x"\n',
    'model = "mine"\nmodel_catalog_json = "/home/me/own.json"\n\n[windows]\nsandbox = "elevated"\n',
]


@pytest.mark.parametrize("original", ORIGINALS)
def test_install_uninstall_restores_config_exactly(svc: SetupService, original: str) -> None:
    svc.config_path.parent.mkdir(parents=True, exist_ok=True)
    svc.config_path.write_bytes(original.encode())
    svc.one_click_setup(KEY, client=make_client())
    assert svc.catalog_file.exists()
    svc.set_mode("personal")
    if "own.json" in original:
        assert cfg(svc)["model_catalog_json"] == "/home/me/own.json"
    svc.set_mode("lunovant")
    svc.uninstall()
    restored = svc.config_path.read_text(encoding="utf-8")
    # byte-exact apart from the trailing blank line tomlkit leaves after a removed table
    assert restored.rstrip() == original.rstrip()
    assert tomllib.loads(restored) == tomllib.loads(original)
    assert not svc.catalog_file.exists() and not svc.profile_file.exists()
    assert svc.ownership().model_catalog is None


def test_uninstall_without_original_config(svc: SetupService) -> None:
    svc.one_click_setup(KEY, client=make_client())
    svc.uninstall()
    assert not svc.catalog_file.exists()
    if svc.config_path.exists():
        assert "model_catalog_json" not in cfg(svc)


def test_rerun_after_failure_removes_stale_key(svc: SetupService, fake: FakeCodex) -> None:
    svc.one_click_setup(KEY, client=make_client())
    assert "model_catalog_json" in cfg(svc)
    fake.failing.add("/b/codex")
    svc.one_click_setup(KEY, client=make_client())
    assert "model_catalog_json" not in cfg(svc) and "model_catalog_json" not in profile(svc)
    assert not svc.catalog_file.exists()


@pytest.mark.parametrize("raw", [r"C:\Users\me\.codex\lunovant-models.json",
                                 "C:/Users/me/.codex/lunovant-models.json"])
def test_windows_paths_are_valid_toml(raw: str) -> None:
    import tomlkit

    from codex_setup.core import codex_config

    doc = tomlkit.parse('model = "x"\n')
    codex_config.set_catalog(doc, raw)
    assert tomllib.loads(tomlkit.dumps(doc))["model_catalog_json"] == raw
    # -c override used for validation is a valid TOML string too
    override = f"model_catalog_json={json.dumps(raw)}"
    assert tomllib.loads(override)["model_catalog_json"] == raw


def test_hidden_sold_model_is_rejected(tmp_path: Path) -> None:
    class Hides(FakeCodex):
        def __call__(self, argv, env, timeout):
            rc, out, err = super().__call__(argv, env, timeout)
            if argv[1:4] == ["debug", "models", "-c"]:
                data = json.loads(out)
                for m in data["models"]:
                    if m["slug"] == "gpt-6.2-sol":
                        m["visibility"] = "hide"
                out = json.dumps(data)
            return rc, out, err

    fake = Hides({"/a/codex": "0.169.0"})
    res = mc.create_catalog(tmp_path, ["gpt-6.1-sol", "gpt-6.2-sol"], default_model=None,
                            env={}, binaries=binaries(fake), runner=fake)
    assert not res.ok and res.note[0] == "catalog_failed"
    assert not list(tmp_path.glob("*lunovant-models*"))


def test_hidden_sold_model_keeps_catalog_out_of_config(svc: SetupService, fake: FakeCodex) -> None:
    orig = fake.__call__

    def hide(argv, env, timeout):
        rc, out, err = orig(argv, env, timeout)
        if list(argv)[1:4] == ["debug", "models", "-c"]:
            data = json.loads(out)
            for m in data["models"]:
                if m["slug"] == "gpt-6.2-sol":
                    m["visibility"] = "hide"
            out = json.dumps(data)
        return rc, out, err

    svc._catalog_runner = hide
    res = svc.one_click_setup(KEY, client=make_client())
    assert res.ok and not res.catalog["ok"]
    assert "model_catalog_json" not in cfg(svc) and not svc.catalog_file.exists()


def test_rerun_validation_failure_keeps_live_file_until_config_is_clean(
        svc: SetupService, fake: FakeCodex) -> None:
    svc.one_click_setup(KEY, client=make_client())
    before = svc.catalog_file.read_bytes()
    seen: list[bytes] = []
    orig = fake.__call__

    def spy(argv, env, timeout):
        if list(argv)[1:4] == ["debug", "models", "-c"]:
            seen.append(svc.catalog_file.read_bytes())  # live file during validation
        return orig(argv, env, timeout)

    fake.failing.add("/b/codex")
    svc._catalog_runner = spy
    svc.one_click_setup(KEY, client=make_client(SOLD_IDS + ["gpt-7-sol"]))
    assert seen and all(b == before for b in seen)  # candidate never replaced the live file
    assert "model_catalog_json" not in cfg(svc) and not svc.catalog_file.exists()


def test_rerun_config_save_failure_leaves_valid_catalog(svc: SetupService, monkeypatch) -> None:
    from codex_setup import app as app_mod
    from codex_setup.core.errors import ConfigWriteError

    svc.one_click_setup(KEY, client=make_client())
    path = str(svc.catalog_file)

    def boom(*a, **k):
        raise ConfigWriteError("disk full")

    with monkeypatch.context() as m:
        m.setattr(app_mod, "save_config", boom)
        with pytest.raises(ConfigWriteError):
            svc.one_click_setup(KEY, client=make_client(SOLD_IDS + ["gpt-7-sol"]))
    # config still points at a file that exists and parses; no candidate is left behind
    assert cfg(svc)["model_catalog_json"] == path
    json.loads(svc.catalog_file.read_text(encoding="utf-8"))
    assert not list(svc.catalog_file.parent.glob(".*.candidate"))


@pytest.mark.parametrize("binaries_found", [True, False])
def test_foreign_catalog_file_is_never_touched(svc: SetupService, monkeypatch,
                                               binaries_found: bool) -> None:
    if not binaries_found:
        monkeypatch.setattr(mc, "find_codex_binaries", lambda **kw: [])
    svc.catalog_file.parent.mkdir(parents=True, exist_ok=True)
    svc.catalog_file.write_text('{"mine": true}', encoding="utf-8")
    res = svc.one_click_setup(KEY, client=make_client())
    assert res.ok and not res.catalog["ok"]
    assert res.catalog["code"] == ("catalog_foreign" if binaries_found else "catalog_no_codex")
    assert svc.catalog_file.read_text(encoding="utf-8") == '{"mine": true}'
    assert "model_catalog_json" not in cfg(svc)
    svc.uninstall()
    assert svc.catalog_file.read_text(encoding="utf-8") == '{"mine": true}'


def test_foreign_file_kept_on_validation_failure(svc: SetupService, fake: FakeCodex) -> None:
    fake.failing.add("/a/codex")
    svc.catalog_file.parent.mkdir(parents=True, exist_ok=True)
    svc.catalog_file.write_text("{}", encoding="utf-8")
    svc.one_click_setup(KEY, client=make_client())
    assert svc.catalog_file.read_text(encoding="utf-8") == "{}"


def test_file_edited_after_setup_survives_uninstall_and_rerun(svc: SetupService) -> None:
    svc.one_click_setup(KEY, client=make_client())
    svc.catalog_file.write_text('{"edited": 1}', encoding="utf-8")
    res = svc.one_click_setup(KEY, client=make_client())
    assert res.catalog["code"] == "catalog_foreign"
    assert svc.catalog_file.read_text(encoding="utf-8") == '{"edited": 1}'
    assert "model_catalog_json" not in cfg(svc) and "model_catalog_json" not in profile(svc)
    svc.uninstall()
    assert svc.catalog_file.read_text(encoding="utf-8") == '{"edited": 1}'


def test_relative_codex_home_is_stored_absolute(fake: FakeCodex, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEX_HOME", "rel-home")
    s = SetupService(secret_store=SecretStore(backend="session"))
    s._platform = PlatformInfo("macos", "25", "arm64")
    s._install = CodexInstall(None, None, False, False, None, None, "n/a")
    s._catalog_runner = fake
    assert s.one_click_setup(KEY, client=make_client()).ok
    value = cfg(s)["model_catalog_json"]
    assert Path(value).is_absolute() and value == str(tmp_path.resolve() / "rel-home" / mc.CATALOG_FILE) \
        or Path(value).samefile(tmp_path / "rel-home" / mc.CATALOG_FILE)
    assert all(c[1]["CODEX_HOME"] == str(tmp_path.resolve() / "rel-home")
               or Path(c[1]["CODEX_HOME"]).is_absolute() for c in fake.calls[1:])
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    assert Path(value).is_file()
    prof = tomllib.loads((tmp_path / "rel-home" / "lunovant.config.toml").read_text(encoding="utf-8"))
    assert prof["model_catalog_json"] == value


# -- refresh_catalog / mode switch ----------------------------------------------------------
def listed(svc: SetupService) -> set[str]:
    data = json.loads(svc.catalog_file.read_text(encoding="utf-8"))
    return {m["slug"] for m in data["models"] if m["visibility"] == "list"}


def install_without_catalog(svc: SetupService, monkeypatch, fake: FakeCodex) -> None:
    """Old-app install: Lunovant is set up but no catalog exists."""
    with monkeypatch.context() as m:
        m.setattr(mc, "find_codex_binaries", lambda **kw: [])
        assert svc.one_click_setup(KEY, client=make_client()).ok
    assert not svc.catalog_file.exists() and "model_catalog_json" not in cfg(svc)
    svc._catalog_runner = fake
    monkeypatch.setattr(mc, "find_codex_binaries", lambda **kw: binaries(fake))


def test_set_mode_lunovant_builds_missing_catalog(svc: SetupService, fake: FakeCodex,
                                                  monkeypatch) -> None:
    install_without_catalog(svc, monkeypatch, fake)
    svc.set_mode("personal")
    svc._http_client = make_client()
    res = svc.set_mode("lunovant")
    path = str(svc.catalog_file)
    assert cfg(svc)["model_catalog_json"] == path and profile(svc)["model_catalog_json"] == path
    assert listed(svc) == {"gpt-6.1-sol", "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6-luna"}
    assert not res.notes and svc.ownership().model_catalog == path


def test_set_mode_catalog_failure_is_only_a_note(svc: SetupService, fake: FakeCodex,
                                                 monkeypatch) -> None:
    install_without_catalog(svc, monkeypatch, fake)
    fake.failing.add("/a/codex")
    svc._http_client = make_client()
    res = svc.set_mode("lunovant")
    assert cfg(svc)["model_provider"] == "lunovant"
    assert [n[0] for n in res.notes] == ["catalog_failed"]
    assert "model_catalog_json" not in cfg(svc) and not svc.catalog_file.exists()


def test_refresh_adds_removes_and_is_idempotent(svc: SetupService) -> None:
    svc.one_click_setup(KEY, client=make_client())
    first = svc.catalog_file.read_bytes()
    same = svc.refresh_catalog(client=make_client())
    assert not same.changed and svc.catalog_file.read_bytes() == first
    mtime = svc.catalog_file.stat().st_mtime_ns
    sha = svc.ownership().model_catalog_sha
    svc.refresh_catalog(client=make_client())
    assert svc.catalog_file.stat().st_mtime_ns == mtime and svc.ownership().model_catalog_sha == sha

    res = svc.refresh_catalog(client=make_client(SOLD_IDS + ["gpt-6.3-sol"]))
    assert res.changed and res.added == ["gpt-6.3-sol"] and res.removed == []
    assert "gpt-6.3-sol" in listed(svc)
    assert svc.ownership().model_catalog_sha != sha
    assert cfg(svc)["model_catalog_json"] == str(svc.catalog_file)

    res = svc.refresh_catalog(client=make_client([m for m in SOLD_IDS if m != "gpt-6-luna"]))
    assert res.changed and set(res.removed) == {"gpt-6-luna", "gpt-6.3-sol"} and res.added == []
    assert "gpt-6-luna" not in listed(svc)
    assert KEY not in svc.catalog_file.read_text(encoding="utf-8")


def test_refresh_invalid_binary_removes_key_and_file(svc: SetupService, fake: FakeCodex) -> None:
    svc.one_click_setup(KEY, client=make_client())
    # config as it is without our catalog key
    # TOML escapes backslashes, so a Windows path is written as "C:\\\\Users\\\\..."
    toml_path = tomlkit.item(str(svc.catalog_file)).as_string()
    line = f"model_catalog_json = {toml_path}\n"
    before = svc.config_path.read_text(encoding="utf-8")
    assert line in before
    expected = before.replace(line, "")
    fake.failing.add("/b/codex")
    res = svc.refresh_catalog(client=make_client(SOLD_IDS + ["gpt-6.3-sol"]))
    assert res.changed and res.code == "removed" and res.params == {"version": "0.169.0-alpha.11.1"}
    assert "model_catalog_json" not in cfg(svc) and "model_catalog_json" not in profile(svc)
    assert not svc.catalog_file.exists() and svc.ownership().model_catalog is None
    assert svc.config_path.read_text(encoding="utf-8") == expected
    from codex_setup.ui import i18n
    i18n.set_lang("vi")
    try:
        assert i18n.refresh_text(res.to_dict()) == (
            "Đã gỡ danh sách model không còn hợp lệ với Codex 0.169.0-alpha.11.1.")
    finally:
        i18n.set_lang("en")


def test_refresh_offline_uses_stored_sold_list(svc: SetupService) -> None:
    svc.one_click_setup(KEY, client=make_client())
    before = svc.catalog_file.read_bytes()

    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    broken = httpx.Client(transport=httpx.MockTransport(down))
    assert not svc.refresh_catalog(client=broken).changed
    assert not svc.refresh_catalog(offline=True, client=make_client(["gpt-9-sol"])).changed
    assert svc.catalog_file.read_bytes() == before and "gpt-6.2-sol" in listed(svc)
    # stored list drives a rebuild when the file is gone (e.g. user deleted it)
    svc.catalog_file.unlink()
    res = svc.refresh_catalog(offline=True)
    assert res.changed and listed(svc) == {"gpt-6.1-sol", "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6-luna"}


def test_refresh_never_touches_foreign_file_and_no_binaries(svc: SetupService,
                                                            monkeypatch) -> None:
    svc.one_click_setup(KEY, client=make_client())
    cfg_before = svc.config_path.read_bytes()
    svc.catalog_file.write_text('{"edited": 1}', encoding="utf-8")
    res = svc.refresh_catalog(client=make_client(SOLD_IDS + ["gpt-6.3-sol"]))
    assert not res.changed and res.note == ("catalog_foreign", {})
    assert svc.catalog_file.read_text(encoding="utf-8") == '{"edited": 1}'
    assert svc.config_path.read_bytes() == cfg_before

    svc.catalog_file.write_bytes(b"")  # restore an owned-looking state is not possible; reinstall
    svc.catalog_file.unlink()
    svc.refresh_catalog(client=make_client())
    good = svc.catalog_file.read_bytes()
    monkeypatch.setattr(mc, "find_codex_binaries", lambda **kw: [])
    res = svc.refresh_catalog(client=make_client(SOLD_IDS + ["gpt-6.3-sol"]))
    assert not res.changed and res.code == "no_codex"
    assert svc.catalog_file.read_bytes() == good


def test_refresh_not_installed_is_noop(svc: SetupService) -> None:
    assert svc.refresh_catalog(client=make_client()).code == "skipped"
    assert not svc.config_path.exists()


def test_refresh_in_personal_mode_updates_profile_only(svc: SetupService) -> None:
    svc.one_click_setup(KEY, client=make_client(), mode="personal")
    res = svc.refresh_catalog(client=make_client(SOLD_IDS + ["gpt-6.3-sol"]))
    assert res.changed and "model_catalog_json" not in cfg(svc)
    assert profile(svc)["model_catalog_json"] == str(svc.catalog_file)


def test_gui_refresh_does_not_hold_lock(svc: SetupService, fake: FakeCodex, monkeypatch) -> None:
    import threading
    import time

    from codex_setup.gui.api import GuiApi

    svc.one_click_setup(KEY, client=make_client())
    svc._http_client = make_client(SOLD_IDS + ["gpt-6.3-sol"])
    gate, entered = threading.Event(), threading.Event()

    def slow_find(**kw):
        entered.set()
        gate.wait(10)  # a fake binary that blocks
        return binaries(fake)

    monkeypatch.setattr(mc, "find_codex_binaries", slow_find)
    api = GuiApi(svc, lang="vi")
    out: dict = {}
    th = threading.Thread(target=lambda: out.update(api.refresh_catalog()))
    th.start()
    try:
        assert entered.wait(5)
        t0 = time.monotonic()
        assert api.status()["ok"]
        assert time.monotonic() - t0 < 1
    finally:
        gate.set()
        th.join(10)
    assert out["ok"] and out["changed"] and out["added"] == ["gpt-6.3-sol"]
    assert out["text"] == "Đã cập nhật danh sách model cho Codex: thêm gpt-6.3-sol"
    assert KEY not in json.dumps(out)


def test_gui_refresh_silent_when_unchanged(svc: SetupService) -> None:
    from codex_setup.gui.api import GuiApi

    svc.one_click_setup(KEY, client=make_client())
    svc._http_client = make_client()
    out = GuiApi(svc, lang="en").refresh_catalog()
    assert out["ok"] and not out["changed"] and out["text"] is None


def test_diagnostics_matches_real_parse_error() -> None:
    from codex_setup.diagnostics.knowledge import lookup

    text = ("Error: failed to parse model_catalog_json path `/home/u/.codex/lunovant-models.json` "
            "as JSON: missing field `display_name` at line 3 column 5")
    found = lookup(text)
    assert [i.id for i in found] == ["model_catalog_invalid"]
    assert "lunovant-setup refresh-catalog" in found[0].steps["vi"][0]
    assert "Mở Lunovant Setup" in found[0].steps["vi"][0]


def test_cli_refresh_catalog_command(svc: SetupService, capsys, monkeypatch) -> None:
    from codex_setup import main as cli

    svc.one_click_setup(KEY, client=make_client())
    svc._http_client = make_client(SOLD_IDS + ["gpt-6.3-sol"])
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    assert cli.main(["--lang", "vi", "refresh-catalog"]) == 0
    assert "thêm gpt-6.3-sol" in capsys.readouterr().out
    assert cli.main(["--lang", "vi", "refresh-catalog", "--offline"]) == 0
    assert capsys.readouterr().out == ""


# -- review fixes ---------------------------------------------------------------------------
def test_concurrent_builds_use_own_candidates(svc: SetupService, fake: FakeCodex,
                                               monkeypatch) -> None:
    install_without_catalog(svc, monkeypatch, fake)
    plan_a, plan_b = svc.catalog_refresh_plan(), svc.catalog_refresh_plan()
    _, built_a = svc.catalog_refresh_run(plan_a, client=make_client(["gpt-6.1-sol"]))
    _, built_b = svc.catalog_refresh_run(plan_b, client=make_client(["gpt-6.2-sol", "gpt-6-luna"]))
    assert built_a.candidate != built_b.candidate
    assert built_a.candidate.is_file() and built_b.candidate.is_file()
    assert svc.catalog_refresh_apply(plan_a, built_a).changed
    assert svc.catalog_refresh_apply(plan_b, built_b).code == "skipped"  # state moved on
    assert listed(svc) == {"gpt-6.1-sol"}
    assert mc.sha256_file(svc.catalog_file) == svc.ownership().model_catalog_sha == built_a.sha
    assert not list(svc.catalog_file.parent.glob(".*.candidate"))


def test_refresh_result_dropped_when_model_changes_or_uninstalled(
        svc: SetupService, fake: FakeCodex, monkeypatch) -> None:
    install_without_catalog(svc, monkeypatch, fake)
    plan = svc.catalog_refresh_plan()
    _, built = svc.catalog_refresh_run(plan, client=make_client())
    svc.change_model("gpt-6.2-sol")
    assert svc.catalog_refresh_apply(plan, built).code == "skipped"
    assert cfg(svc)["model"] == "gpt-6.2-sol" and profile(svc)["model"] == "gpt-6.2-sol"
    assert not svc.catalog_file.exists() and "model_catalog_json" not in cfg(svc)

    plan = svc.catalog_refresh_plan()
    _, built = svc.catalog_refresh_run(plan, client=make_client())
    svc.uninstall()
    assert svc.catalog_refresh_apply(plan, built).code == "skipped"
    assert not svc.catalog_file.exists() and not svc.profile_file.exists()
    assert not list(svc.catalog_file.parent.glob(".*.candidate"))


def test_cli_refresh_dry_run_writes_nothing(svc: SetupService, capsys, monkeypatch) -> None:
    from codex_setup import main as cli
    from codex_setup.core import paths

    svc.one_click_setup(KEY, client=make_client())
    svc._http_client = make_client(SOLD_IDS + ["gpt-6.3-sol"])
    monkeypatch.setattr(cli, "make_service", lambda: svc)

    def snap():
        files = [svc.config_path, svc.profile_file, svc.catalog_file,
                 *[p for p in paths.app_state_dir().rglob("*") if p.is_file()]]
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in files}

    before = snap()
    assert cli.main(["refresh-catalog", "--dry-run"]) == 1
    assert snap() == before


def _counting_client(calls: list):
    inner = make_client()

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        return httpx.Response(500)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("fails", [False, True])
def test_cli_mode_offline_never_calls_http(svc: SetupService, fake: FakeCodex, monkeypatch,
                                           fails: bool) -> None:
    from codex_setup import main as cli

    install_without_catalog(svc, monkeypatch, fake)
    svc.set_mode("personal")
    calls: list = []
    svc._http_client = _counting_client(calls)
    if fails:
        fake.failing.add("/b/codex")
    monkeypatch.setattr(cli, "make_service", lambda: svc)
    assert cli.main(["mode", "lunovant", "--offline", "--yes"]) == 0
    assert calls == []
    assert cfg(svc)["model_provider"] == "lunovant"
    assert svc.catalog_file.exists() is (not fails)
    assert ("model_catalog_json" in cfg(svc)) is (not fails)


def test_refresh_empty_models_answer_still_validates_stored_list(
        svc: SetupService, fake: FakeCodex) -> None:
    svc.one_click_setup(KEY, client=make_client())
    fake.failing.add("/b/codex")
    res = svc.refresh_catalog(client=make_client([]))
    assert res.changed and res.code == "removed"
    assert "model_catalog_json" not in cfg(svc) and "model_catalog_json" not in profile(svc)
    assert not svc.catalog_file.exists()
