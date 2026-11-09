from __future__ import annotations

import difflib
import tomllib

import pytest
import tomlkit

from codex_setup.core import codex_config as cc
from codex_setup.core.config_store import render
from codex_setup.core.errors import ReservedProviderError
from codex_setup.providers.catalog import LUNOVANT, custom_provider

FIXTURES = ["windows_config.toml", "macos_config.toml", "linux_config.toml"]
EMPTY_CASES = ["", "[tui]\nx = 1\n", "# only comment\n"]


def _doc(text: str):
    return tomlkit.parse(text)


def _changed_lines(old: str, new: str) -> list[str]:
    """Lines removed from old (ignoring newline style)."""
    o = old.replace("\r\n", "\n").splitlines()
    n = new.replace("\r\n", "\n").splitlines()
    return [d[2:] for d in difflib.ndiff(o, n) if d.startswith("- ")]


def _assert_preserved(old: str, new: str, allowed_removed: tuple[str, ...] = ()) -> None:
    for line in _changed_lines(old, new):
        assert line.startswith(allowed_removed) if allowed_removed else False, line


@pytest.mark.parametrize("name", FIXTURES)
def test_upsert_preserves_and_parses(name: str, fixture_text) -> None:
    old = fixture_text(name)
    doc = _doc(old)
    cc.upsert_provider(doc, LUNOVANT)
    cc.set_active(doc, "lunovant", "gpt-6.1-sol")
    new = render(doc)
    data = tomllib.loads(new)
    assert data["model"] == "gpt-6.1-sol" and data["model_provider"] == "lunovant"
    assert data["model_providers"]["lunovant"]["base_url"] == "https://api.lunovant.tech/v1"
    assert data["model_providers"]["lunovant"]["env_key"] == "LUNOVANT_API_KEY"
    # other data untouched
    before = tomllib.loads(old)
    for key, value in before.items():
        if key in ("model", "model_provider", "model_providers"):
            continue
        assert data[key] == value
    for pid, value in before.get("model_providers", {}).items():
        if pid != "lunovant":
            assert data["model_providers"][pid] == value
    # only expected lines were removed
    _assert_preserved(
        old, new, ("model = ", "model_provider = ", "name = ", "base_url = ", "env_key = ")
    )


@pytest.mark.parametrize("name", FIXTURES)
def test_comments_survive(name: str, fixture_text) -> None:
    old = fixture_text(name)
    doc = _doc(old)
    cc.upsert_provider(doc, LUNOVANT)
    cc.set_active(doc, "lunovant", "gpt-6.1-sol")
    new = render(doc).replace("\r\n", "\n")
    for line in old.replace("\r\n", "\n").splitlines():
        if line.lstrip().startswith("#"):
            assert line in new


def test_vietnamese_and_trailing_comments_kept(fixture_text) -> None:
    doc = _doc(fixture_text("linux_config.toml"))
    cc.upsert_provider(doc, LUNOVANT)
    out = render(doc)
    assert "# giữ header" in out and "# Cấu hình Codex trên Linux" in out
    assert out.count("[model_providers.lunovant]") == 1
    assert 'http_headers = { "X-Team" = "mobile" }' in out
    data = tomllib.loads(out)
    assert data["model_providers"]["lunovant"]["http_headers"] == {"X-Team": "mobile"}
    assert data["model_providers"]["lunovant"]["base_url"] == LUNOVANT.base_url
    assert data["model_providers"]["lunovant"]["name"] == "Lunovant"


@pytest.mark.parametrize("text", EMPTY_CASES)
def test_set_active_top_level_before_tables(text: str) -> None:
    doc = _doc(text)
    cc.upsert_provider(doc, LUNOVANT)
    cc.set_active(doc, "lunovant", "gpt-6.1-sol")
    data = tomllib.loads(render(doc))
    assert data["model"] == "gpt-6.1-sol"
    assert data["model_provider"] == "lunovant"
    assert "model" not in data.get("tui", {}) and "model" not in data["model_providers"]["lunovant"]


def test_top_level_not_inside_last_table(fixture_text) -> None:
    doc = _doc(fixture_text("windows_config.toml"))
    cc.set_active(doc, "lunovant", "m1")
    data = tomllib.loads(render(doc))
    assert data["model"] == "m1"
    assert "model" not in data["mcp_servers"]["tools"]
    assert "model" not in data["windows"]


def test_no_duplicate_tables_on_repeat(fixture_text) -> None:
    doc = _doc(fixture_text("macos_config.toml"))
    for _ in range(3):
        cc.upsert_provider(doc, LUNOVANT)
        cc.set_active(doc, "lunovant", "gpt-6.1-sol")
    out = render(doc)
    assert out.count("[model_providers.lunovant]") == 1
    data = tomllib.loads(out)
    assert sorted(data["model_providers"]) == ["azure", "lunovant", "other"]
    assert out.count("\nmodel = ") + out.startswith("model = ") == 1


def test_other_providers_byte_identical(fixture_text) -> None:
    old = fixture_text("macos_config.toml")
    doc = _doc(old)
    cc.upsert_provider(doc, LUNOVANT)
    new = render(doc)
    block = old[old.index("[model_providers.azure]") : old.index("# MCP servers")]
    assert block in new
    assert old[old.index("# MCP servers") :] in new


def test_dotted_keys_updated_in_place() -> None:
    text = (
        'model_providers.lunovant.base_url = "https://old/v1"\n'
        'model_providers.lunovant.http_headers = { a = "b" }\n'
        "\n[tui]\nx = 1\n"
    )
    doc = _doc(text)
    cc.upsert_provider(doc, LUNOVANT)
    cc.set_active(doc, "lunovant", "gpt-6.1-sol")
    out = render(doc)
    data = tomllib.loads(out)
    assert data["model_providers"]["lunovant"]["base_url"] == LUNOVANT.base_url
    assert data["model_providers"]["lunovant"]["http_headers"] == {"a": "b"}
    assert out.count("base_url") == 1
    assert "[model_providers.lunovant]" not in out
    assert data["model"] == "gpt-6.1-sol" and data["tui"] == {"x": 1}


def test_existing_extra_keys_kept(fixture_text) -> None:
    doc = _doc(fixture_text("linux_config.toml"))
    cc.upsert_provider(doc, custom_provider("lunovant", "New", "https://n.io/v1", "NEW_KEY"))
    data = tomllib.loads(render(doc))["model_providers"]["lunovant"]
    assert data["env_key"] == "NEW_KEY" and data["name"] == "New"
    assert data["http_headers"] == {"X-Team": "mobile"}


@pytest.mark.parametrize("pid", sorted(cc.RESERVED_PROVIDER_IDS))
def test_reserved_ids(pid: str) -> None:
    from codex_setup.providers.catalog import ProviderSpec

    doc = _doc("")
    with pytest.raises(ReservedProviderError):
        cc.upsert_provider(doc, ProviderSpec(pid, "x", "https://x.io", "K"))
    assert render(doc) == ""


@pytest.mark.parametrize("name", FIXTURES)
def test_remove_provider_roundtrip(name: str, fixture_text) -> None:
    old = fixture_text(name).replace("\r\n", "\n")
    doc = _doc(old)
    had_lunovant = "[model_providers.lunovant]" in old
    assert cc.remove_provider(doc, "lunovant") is had_lunovant
    cc.upsert_provider(doc, LUNOVANT)
    assert cc.remove_provider(doc, "lunovant") is True
    data = tomllib.loads(render(doc))
    assert "lunovant" not in data.get("model_providers", {})
    before = tomllib.loads(old)
    for pid in before.get("model_providers", {}):
        if pid != "lunovant":
            assert data["model_providers"][pid] == before["model_providers"][pid]
    if not had_lunovant:
        assert render(doc).strip() == old.strip()


def test_remove_last_provider_drops_super_table() -> None:
    doc = _doc("")
    cc.upsert_provider(doc, LUNOVANT)
    cc.remove_provider(doc, "lunovant")
    assert "model_providers" not in tomllib.loads(render(doc))


def test_set_model_and_restore_top_level(fixture_text) -> None:
    doc = _doc(fixture_text("macos_config.toml"))
    cc.set_model(doc, "gpt-6-luna")
    assert tomllib.loads(render(doc))["model"] == "gpt-6-luna"
    cc.restore_top_level(doc, "gpt-5", "azure")
    data = tomllib.loads(render(doc))
    assert (data["model"], data["model_provider"]) == ("gpt-5", "azure")
    cc.restore_top_level(doc, None, None)
    data = tomllib.loads(render(doc))
    assert "model" not in data and "model_provider" not in data
    assert "azure" in data["model_providers"]


def test_restore_top_level_adds_on_missing() -> None:
    doc = _doc("[tui]\nx = 1\n")
    cc.restore_top_level(doc, "m", "p")
    data = tomllib.loads(render(doc))
    assert data["model"] == "m" and data["model_provider"] == "p" and data["tui"] == {"x": 1}


def test_windows_sandbox(fixture_text) -> None:
    doc = _doc(fixture_text("windows_config.toml"))
    assert cc.get_status(doc).windows_sandbox == "elevated"
    cc.set_windows_sandbox(doc, "unelevated")
    assert tomllib.loads(render(doc))["windows"]["sandbox"] == "unelevated"
    cc.set_windows_sandbox(doc, None)
    assert "windows" not in tomllib.loads(render(doc))
    cc.set_windows_sandbox(doc, "elevated")
    data = tomllib.loads(render(doc))
    assert data["windows"] == {"sandbox": "elevated"}
    assert data["mcp_servers"]["tools"]["command"].startswith("C:\\Program")


def test_windows_sandbox_keeps_other_keys() -> None:
    doc = _doc('[windows]\nsandbox = "elevated"\nother = 1\n')
    cc.set_windows_sandbox(doc, None)
    assert tomllib.loads(render(doc)) == {"windows": {"other": 1}}
    empty = _doc("")
    cc.set_windows_sandbox(empty, None)
    assert render(empty) == ""
    cc.set_windows_sandbox(empty, "unelevated")
    assert tomllib.loads(render(empty)) == {"windows": {"sandbox": "unelevated"}}


def test_get_status(fixture_text) -> None:
    status = cc.get_status(_doc(fixture_text("macos_config.toml")))
    assert status.model == "gpt-5" and status.model_provider == "azure"
    assert status.provider_ids == ["azure", "other"]
    assert status.active_provider and status.active_provider["env_key"] == "AZURE_OPENAI_API_KEY"
    assert status.windows_sandbox is None
    empty = cc.get_status(_doc(""))
    assert empty.model is None and empty.provider_ids == [] and empty.active_provider is None
