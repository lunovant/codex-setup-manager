import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from codex_setup.core.errors import ValidationError
from codex_setup.platforms import shellrc


def test_choose_rc(tmp_path):
    assert shellrc.choose_rc("/bin/zsh", tmp_path) == tmp_path / ".zshrc"
    assert shellrc.choose_rc("/usr/bin/bash", tmp_path) == tmp_path / ".bashrc"
    assert shellrc.choose_rc("/bin/fish", tmp_path) == tmp_path / ".profile"
    assert shellrc.choose_rc(None, tmp_path) == tmp_path / ".profile"


def test_install_preserves_and_backs_up(tmp_path):
    rc = tmp_path / ".zshrc"
    rc.write_text("alias a=b\n")
    os.chmod(rc, 0o640)
    backup = shellrc.install_block(rc, "K", "v1")
    assert backup and backup.read_text() == "alias a=b\n"
    assert backup.name.startswith(".zshrc.codex-setup-backup-")
    text = rc.read_text()
    assert text.startswith("alias a=b\n") and "export K='v1'" in text
    assert shellrc.has_block(rc)
    if sys.platform != "win32":
        assert stat.S_IMODE(rc.stat().st_mode) == 0o640
    shellrc.install_block(rc, "K", "v2")
    text = rc.read_text()
    assert text.count(shellrc.START) == 1 and "v2" in text and "v1" not in text


def test_remove_restores_content(tmp_path):
    rc = tmp_path / ".bashrc"
    rc.write_text("x=1\n")
    shellrc.install_block(rc, "K", "v")
    assert shellrc.remove_block(rc, "K") is True
    assert rc.read_text() == "x=1\n" and not shellrc.has_block(rc)
    assert shellrc.remove_block(rc, "K") is False
    assert shellrc.remove_block(tmp_path / "none", "K") is False


def test_new_file_is_private(tmp_path):
    rc = tmp_path / ".profile"
    assert shellrc.install_block(rc, "K", "v") is None
    if sys.platform != "win32":
        assert stat.S_IMODE(rc.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="needs sh")
def test_quote_roundtrip_in_shell(tmp_path):
    value = "a'b\"c $x `y` \\"
    rc = tmp_path / ".profile"
    shellrc.install_block(rc, "K", value)
    out = subprocess.run(["sh", "-c", f". '{rc}'; printf %s \"$K\""], capture_output=True, text=True)
    assert out.stdout == value


def test_validation(tmp_path):
    with pytest.raises(ValidationError):
        shellrc.install_block(tmp_path / "rc", "bad-name", "v")
    with pytest.raises(ValidationError):
        shellrc.install_block(tmp_path / "rc", "K", "a\nb")
