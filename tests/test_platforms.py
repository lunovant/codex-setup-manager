import plistlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

from codex_setup.platforms.base import PlatformInfo, detect_codex, detect_platform, parse_cli_version


def fake_run(stdout="codex-cli 0.162.1\n", exc=None):
    def run(argv, **kw):
        if exc:
            raise exc
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    return run


def mac_app(root: Path, name="ChatGPT.app", bundle="com.openai.codex"):
    app = root / name
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "ChatGPT").write_text("")
    (app / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleIdentifier": bundle, "CFBundleExecutable": "ChatGPT"})
    )
    return app


MAC = PlatformInfo("macos", "25", "arm64")


def test_version_parse():
    assert parse_cli_version("codex-cli 0.162.1") == "0.162.1"
    assert parse_cli_version("nothing") is None


def test_cli_version_and_errors():
    which = lambda n: "/bin/codex"
    r = detect_codex(MAC, which=which, run=fake_run(), env={}, roots=[])
    assert (r.cli_path, r.cli_version) == ("/bin/codex", "0.162.1")
    for exc in (subprocess.TimeoutExpired("c", 5), FileNotFoundError()):
        r = detect_codex(MAC, which=which, run=fake_run(exc=exc), env={}, roots=[])
        assert r.cli_version is None
    r = detect_codex(MAC, which=lambda n: None, run=fake_run(), env={}, roots=[])
    assert r.cli_path is None and r.cli_version is None


def test_macos_bundle(tmp_path):
    root = tmp_path / "Applications"
    app = mac_app(root)
    r = detect_codex(MAC, which=lambda n: None, run=fake_run(), env={}, roots=[root])
    assert r.desktop_installed and r.desktop_path == str(app)
    assert r.desktop_executable == str(app / "Contents/MacOS/ChatGPT")


def test_macos_wrong_bundle_and_codex_dir(tmp_path):
    root = tmp_path / "Applications"
    mac_app(root, bundle="com.other")
    (tmp_path / "home" / ".codex").mkdir(parents=True)
    r = detect_codex(MAC, which=lambda n: None, run=fake_run(), env={"HOME": str(tmp_path / "home")}, roots=[root])
    assert not r.desktop_installed and r.desktop_supported


def test_windows(tmp_path):
    local = tmp_path / "Local"
    plat = PlatformInfo("windows", "11", "AMD64")
    r = detect_codex(plat, which=lambda n: None, run=fake_run(), env={"LOCALAPPDATA": str(local)})
    assert not r.desktop_installed and "not detected" in r.desktop_note
    exe = local / "Programs" / "Codex" / "Codex.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    r = detect_codex(plat, which=lambda n: None, run=fake_run(), env={"LOCALAPPDATA": str(local)})
    assert r.desktop_installed and r.desktop_executable == str(exe)


def test_windows_codex_dir_not_evidence(tmp_path):
    (tmp_path / "Local" / ".codex").mkdir(parents=True)
    plat = PlatformInfo("windows", "11", "AMD64")
    r = detect_codex(plat, which=lambda n: None, run=fake_run(), env={"LOCALAPPDATA": str(tmp_path / "Local")})
    assert not r.desktop_installed


OS_UBUNTU_2204 = 'ID=ubuntu\nVERSION_ID="22.04"\n'
OS_UBUNTU_2404 = 'ID=ubuntu\nVERSION_ID="24.04"\n'


def test_detect_platform_linux_text():
    p = detect_platform(system="linux", os_release=OS_UBUNTU_2404)
    assert (p.system, p.distro_id, p.distro_version) == ("linux", "ubuntu", "24.04")


def test_linux_2204_unsupported():
    p = detect_platform(system="linux", os_release=OS_UBUNTU_2204)
    r = detect_codex(p, which=lambda n: "/usr/bin/chatgpt" if n == "chatgpt" else None, run=fake_run(), env={})
    assert not r.desktop_supported and "22.04" in r.desktop_note


def test_linux_2404_installed_and_missing(tmp_path):
    f = tmp_path / "os-release"
    f.write_text(OS_UBUNTU_2404)
    p = detect_platform(system="linux", os_release=f)
    r = detect_codex(p, which=lambda n: "/usr/bin/chatgpt" if n == "chatgpt" else None, run=fake_run(), env={})
    assert r.desktop_supported and r.desktop_installed and r.desktop_executable == "/usr/bin/chatgpt"
    (tmp_path / "home" / ".codex").mkdir(parents=True)
    r = detect_codex(p, which=lambda n: None, run=fake_run(), env={})
    assert not r.desktop_installed


def test_linux_other_distros():
    for text, ok in [("ID=debian\nVERSION_ID=13\n", True), ("ID=fedora\nVERSION_ID=43\n", True),
                     ("ID=arch\n", True), ("ID=alpine\nVERSION_ID=3.20\n", False)]:
        p = detect_platform(system="linux", os_release=text)
        assert detect_codex(p, which=lambda n: None, run=fake_run(), env={}).desktop_supported is ok


def test_detect_platform_other():
    assert detect_platform(system="darwin").system == "macos"
    assert detect_platform(system="win32").system == "windows"
