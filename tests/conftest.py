from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Point every home-like location at tmp dirs so tests never touch real data."""
    env = {
        "HOME": str(tmp_path / "home"),
        "USERPROFILE": str(tmp_path / "home"),
        "CODEX_HOME": str(tmp_path / "codex_home"),
        "CODEX_SETUP_HOME": str(tmp_path / "setup_home"),
        "APPDATA": str(tmp_path / "appdata"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


@pytest.fixture
def fixture_text():
    def read(name: str) -> str:
        return (FIXTURES / name).read_bytes().decode("utf-8")

    return read


@pytest.fixture
def make_config(tmp_path: Path):
    """Copy a fixture byte-for-byte into tmp and return its path."""

    def make(name: str) -> Path:
        dest = tmp_path / "cfg" / "config.toml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((FIXTURES / name).read_bytes())
        return dest

    return make
