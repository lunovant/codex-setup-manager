from __future__ import annotations

import pytest

from codex_setup.core.errors import ReservedProviderError, ValidationError
from codex_setup.providers import catalog


@pytest.mark.parametrize(
    "raw,expected",
    [
        (" https://api.x.com/ ", "https://api.x.com"),
        ("http://localhost:8080/v1/", "http://localhost:8080/v1"),
        ("https://a.b/v1//", "https://a.b/v1"),
    ],
)
def test_normalize_ok(raw: str, expected: str) -> None:
    assert catalog.normalize_base_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "ftp://x.com", "api.x.com", "https://", "not a url"])
def test_normalize_bad(raw: str) -> None:
    with pytest.raises(ValidationError):
        catalog.normalize_base_url(raw)


def test_suggest_v1() -> None:
    assert catalog.suggest_v1("https://api.lunovant.tech") == "https://api.lunovant.tech/v1"
    assert catalog.suggest_v1("https://api.lunovant.tech/") == "https://api.lunovant.tech/v1"
    assert catalog.suggest_v1("https://api.lunovant.tech/v1") == "https://api.lunovant.tech/v1"
    assert catalog.suggest_v1("https://api.lunovant.tech/v1/") == "https://api.lunovant.tech/v1"


def test_model_validation() -> None:
    assert catalog.validate_model_name(" gpt-6.1-sol ") == "gpt-6.1-sol"
    for bad in ["", "   ", "a b", 'a"b', "a'b", "x" * 129]:
        with pytest.raises(ValidationError):
            catalog.validate_model_name(bad)


def test_custom_provider_validation() -> None:
    spec = catalog.custom_provider("my-prov_1", "Mine", "https://x.io/", "MY_KEY")
    assert spec.base_url == "https://x.io" and spec.env_key == "MY_KEY"
    for bad_id in ["", "Upper", "-lead", "a b", "x" * 65]:
        with pytest.raises(ValidationError):
            catalog.custom_provider(bad_id, "n", "https://x.io", "K")
    for bad_env in ["lower", "1ABC", "A-B", ""]:
        with pytest.raises(ValidationError):
            catalog.custom_provider("ok", "n", "https://x.io", bad_env)
    with pytest.raises(ReservedProviderError):
        catalog.custom_provider("openai", "n", "https://x.io", "K")


def test_spec_round_trip() -> None:
    assert catalog.ProviderSpec.from_dict(catalog.LUNOVANT.to_dict()) == catalog.LUNOVANT
    assert catalog.LUNOVANT.base_url == catalog.suggest_v1(catalog.LUNOVANT_ROOT_URL)
