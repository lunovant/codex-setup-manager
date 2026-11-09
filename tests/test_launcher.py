import subprocess
from types import SimpleNamespace

import pytest

from codex_setup.core.errors import CodexSetupError
from codex_setup.platforms.base import CodexInstall, PlatformInfo
from codex_setup.security.launcher import build_env, launch_cli, launch_desktop


def install(**kw):
    d = dict(cli_path=None, cli_version=None, desktop_supported=True, desktop_installed=True,
             desktop_path="/x", desktop_executable="/x/bin", desktop_note="")
    d.update(kw)
    return CodexInstall(**d)


def plat(system):
    return PlatformInfo(system, "1", "x")


def test_build_env_copies():
    base = {"A": "1"}
    env = build_env(base, "K", "s")
    assert env == {"A": "1", "K": "s"} and base == {"A": "1"}


def test_launch_cli():
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        return SimpleNamespace(returncode=3)

    assert launch_cli(["exec", "hi"], "K", "SEC", codex_path="/bin/codex", run=run) == 3
    argv, kw = calls[0]
    assert argv == ["/bin/codex", "exec", "hi"]
    assert kw["env"]["K"] == "SEC" and "shell" not in kw
    assert "SEC" not in " ".join(argv)


@pytest.mark.parametrize("system", ["macos", "windows", "linux"])
def test_launch_desktop(system):
    calls = []
    launch_desktop(install(), plat(system), "K", "SEC", popen=lambda *a, **k: calls.append((a, k)))
    (argv,), kw = calls[0]
    assert argv == ["/x/bin"] and kw["env"]["K"] == "SEC"
    assert kw["stdin"] == subprocess.DEVNULL
    if system == "windows":
        assert "creationflags" in kw
    else:
        assert kw["start_new_session"] is True


def test_launch_desktop_errors():
    with pytest.raises(CodexSetupError):
        launch_desktop(install(desktop_installed=False), plat("macos"), "K", "s", popen=lambda *a, **k: None)
    with pytest.raises(CodexSetupError):
        launch_desktop(install(desktop_supported=False), plat("linux"), "K", "s", popen=lambda *a, **k: None)
