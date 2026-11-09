import json
import os
import stat
import sys

import pytest

from codex_setup.core.errors import SecretStoreError
from codex_setup.security.secrets import SERVICE, SecretStore


class FakeKeyring:
    def __init__(self, backend=None):
        self.data = {}
        self._backend = backend if backend is not None else object()

    def get_keyring(self):
        return self._backend

    def get_password(self, service, name):
        return self.data.get((service, name))

    def set_password(self, service, name, value):
        self.data[(service, name)] = value

    def delete_password(self, service, name):
        self.data.pop((service, name))


def test_keyring_roundtrip():
    kr = FakeKeyring()
    s = SecretStore("auto", keyring_module=kr)
    assert s.backend_name == "keyring"
    assert s.get("K") is None
    assert s.delete("K") is False
    s.set("K", "v")
    assert kr.data[(SERVICE, "K")] == "v"
    assert s.get("K") == "v"
    assert s.delete("K") is True


def test_unusable_backends():
    from keyring.backends import chainer, fail, null

    assert not SecretStore.keyring_usable(FakeKeyring(fail.Keyring()))
    assert not SecretStore.keyring_usable(FakeKeyring(null.Keyring()))
    assert SecretStore("auto", keyring_module=FakeKeyring(fail.Keyring())).backend_name == "session"


def test_chainer_without_backends(monkeypatch):
    from keyring.backends import chainer

    monkeypatch.setattr(chainer.ChainerBackend, "backends", [])
    ch = object.__new__(chainer.ChainerBackend)
    assert not SecretStore.keyring_usable(FakeKeyring(ch))


def test_exception_means_unusable():
    class Boom:
        def get_keyring(self):
            raise RuntimeError("x")

    assert not SecretStore.keyring_usable(Boom())


def test_keyring_failure_wrapped():
    class Bad(FakeKeyring):
        def set_password(self, *a):
            raise RuntimeError("locked")

    with pytest.raises(SecretStoreError):
        SecretStore("keyring", keyring_module=Bad()).set("K", "v")


def test_session():
    s = SecretStore("session")
    s.set("K", "v")
    assert s.get("K") == "v"
    assert s.delete("K") and not s.delete("K")


def test_file_backend(isolated_env):
    s = SecretStore("file")
    s.set("K", "secret-value")
    path = os.path.join(isolated_env["CODEX_SETUP_HOME"], "secrets.json")
    assert json.loads(open(path).read()) == {"K": "secret-value"}
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    s.set("K2", "x")
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert SecretStore("file").get("K") == "secret-value"
    assert s.delete("K") and s.get("K") is None


def test_empty_secret_rejected():
    with pytest.raises(SecretStoreError):
        SecretStore("session").set("K", "")


def test_auto_never_picks_file():
    from keyring.backends import fail

    assert SecretStore("auto", keyring_module=FakeKeyring(fail.Keyring())).backend_name != "file"
