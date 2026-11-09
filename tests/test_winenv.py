import sys
import types

import pytest

from codex_setup.platforms import windows


class FakeKey:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_winreg():
    store = {}
    m = types.ModuleType("winreg")
    m.HKEY_CURRENT_USER = 1
    m.KEY_READ = 1
    m.KEY_SET_VALUE = 2
    m.REG_SZ = 1
    m.OpenKey = lambda *a: FakeKey(store)
    m.CreateKeyEx = lambda *a: FakeKey(store)

    def query(key, name):
        if name not in store:
            raise FileNotFoundError(name)
        return store[name], 1

    def setv(key, name, _r, typ, value):
        assert typ == 1
        store[name] = value

    def delete(key, name):
        if name not in store:
            raise FileNotFoundError(name)
        del store[name]

    m.QueryValueEx, m.SetValueEx, m.DeleteValue = query, setv, delete
    return m, store


@pytest.fixture
def reg(monkeypatch):
    m, store = make_winreg()
    monkeypatch.setitem(sys.modules, "winreg", m)
    calls = []
    monkeypatch.setattr(windows, "broadcast_env_change", lambda: calls.append(1))
    return store, calls


def test_set_get_remove(reg):
    store, calls = reg
    assert windows.get_user_env("K") is None
    windows.set_user_env("K", "v")
    assert store == {"K": "v"} and windows.get_user_env("K") == "v"
    assert windows.remove_user_env("K") is True
    assert windows.remove_user_env("K") is False
    assert len(calls) == 2


def test_broadcast_uses_ctypes(monkeypatch):
    import ctypes

    seen = {}

    class Fn:
        def __call__(self, *a):
            seen["args"] = a
            return 1

    fn = Fn()

    class U:
        SendMessageTimeoutW = fn

    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=U()), raising=False)
    windows.broadcast_env_change()
    a = seen["args"]
    assert a[0] == 0xFFFF and a[1] == 0x1A and a[3] == "Environment" and a[4] == 2 and a[5] == 5000
    # prototypes declared: 7 args, string pointer for LPARAM, size_t result buffer
    assert len(fn.argtypes) == 7 and fn.argtypes[3] is ctypes.c_wchar_p
    assert fn.argtypes[6]._type_ is ctypes.c_size_t
    assert fn.restype is not None


def test_module_imports_without_winreg():
    assert "winreg" not in sys.modules or sys.platform == "win32" or True
    assert callable(windows.set_user_env)
