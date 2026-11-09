from __future__ import annotations

from pathlib import Path

from codex_setup.core import paths


def test_codex_home_env_priority(tmp_path: Path) -> None:
    env = {"CODEX_HOME": str(tmp_path / "x"), "HOME": str(tmp_path / "h")}
    assert paths.codex_home(env) == tmp_path / "x"
    assert paths.config_path(env) == tmp_path / "x" / "config.toml"
    assert paths.profile_config_path("work", env) == tmp_path / "x" / "work.config.toml"


def test_empty_codex_home_ignored(tmp_path: Path) -> None:
    env = {"CODEX_HOME": "  ", "HOME": str(tmp_path)}
    assert paths.codex_home(env, system="linux") == tmp_path / ".codex"


def test_default_home_per_os(tmp_path: Path) -> None:
    assert paths.codex_home({"HOME": str(tmp_path / "m")}, system="macos") == tmp_path / "m" / ".codex"
    assert paths.codex_home({"HOME": str(tmp_path / "l")}, system="linux") == tmp_path / "l" / ".codex"
    assert (
        paths.codex_home({"USERPROFILE": str(tmp_path / "w")}, system="windows")
        == tmp_path / "w" / ".codex"
    )


def test_codex_home_tilde(tmp_path: Path) -> None:
    env = {"CODEX_HOME": "~/custom", "HOME": str(tmp_path)}
    assert paths.codex_home(env, system="linux") == tmp_path / "custom"


def test_app_state_dir_per_os(tmp_path: Path) -> None:
    home = str(tmp_path / "home")
    win = {"APPDATA": str(tmp_path / "ad"), "USERPROFILE": home}
    assert paths.app_state_dir(win, system="windows") == tmp_path / "ad" / "codex-setup-manager"
    mac = {"HOME": home}
    assert (
        paths.app_state_dir(mac, system="macos")
        == tmp_path / "home" / "Library" / "Application Support" / "codex-setup-manager"
    )
    assert paths.app_state_dir(mac, system="linux") == tmp_path / "home" / ".config" / "codex-setup-manager"
    xdg = {"HOME": home, "XDG_CONFIG_HOME": str(tmp_path / "xdg")}
    assert paths.app_state_dir(xdg, system="linux") == tmp_path / "xdg" / "codex-setup-manager"


def test_setup_home_override_and_backups(tmp_path: Path) -> None:
    env = {"CODEX_SETUP_HOME": str(tmp_path / "s"), "HOME": str(tmp_path)}
    for system in ("windows", "macos", "linux"):
        assert paths.app_state_dir(env, system=system) == tmp_path / "s"
    assert paths.backups_dir(env) == tmp_path / "s" / "backups"


def test_nothing_is_created(tmp_path: Path) -> None:
    env = {"CODEX_HOME": str(tmp_path / "nope"), "CODEX_SETUP_HOME": str(tmp_path / "nope2")}
    paths.config_path(env)
    paths.backups_dir(env)
    assert not (tmp_path / "nope").exists()
    assert not (tmp_path / "nope2").exists()
