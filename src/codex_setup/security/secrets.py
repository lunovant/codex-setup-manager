"""Secret storage: OS keyring, session memory, or an opt-in 0600 file."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Mapping
from typing import Any

from codex_setup.core import paths
from codex_setup.core.errors import SecretStoreError

SERVICE = "codex-setup-manager"


def _load_keyring(keyring_module: Any = None) -> Any:
    if keyring_module is not None:
        return keyring_module
    import keyring

    return keyring


class SecretStore:
    def __init__(
        self,
        backend: str = "auto",
        env: Mapping[str, str] | None = None,
        keyring_module: Any = None,
    ) -> None:
        if backend not in ("auto", "keyring", "file", "session"):
            raise SecretStoreError(f"Unknown secret backend: {backend}")
        self._env = env
        self._keyring_module = keyring_module
        self._session: dict[str, str] = {}
        if backend == "auto":
            backend = "keyring" if self.keyring_usable(keyring_module) else "session"
        elif backend == "keyring" and not self.keyring_usable(keyring_module):
            raise SecretStoreError("No usable OS keyring backend is available.")
        self.backend_name = backend

    # -- keyring -----------------------------------------------------------
    @staticmethod
    def keyring_usable(keyring_module: Any = None) -> bool:
        try:
            kr = _load_keyring(keyring_module)
            current = kr.get_keyring()
            from keyring.backends import chainer, fail, null

            if isinstance(current, (fail.Keyring, null.Keyring)):
                return False
            if isinstance(current, chainer.ChainerBackend):
                if not list(current.backends):
                    return False
            return True
        except Exception:
            return False

    def _kr(self) -> Any:
        return _load_keyring(self._keyring_module)

    # -- file --------------------------------------------------------------
    def _file_path(self):
        return paths.app_state_dir(self._env) / "secrets.json"

    def _read_file(self) -> dict[str, str]:
        path = self._file_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SecretStoreError(f"Cannot read secrets file {path}: {exc.__class__.__name__}") from exc
        if not isinstance(data, dict):
            raise SecretStoreError(f"Secrets file {path} is malformed.")
        return {str(k): str(v) for k, v in data.items()}

    def _write_file(self, data: dict[str, str]) -> None:
        path = self._file_path()
        tmp_name = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".secrets-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(data))
                fh.flush()
                os.fsync(fh.fileno())
            if sys.platform != "win32":
                os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, path)
            tmp_name = None
        except OSError as exc:
            raise SecretStoreError(f"Cannot write secrets file {path}: {exc.__class__.__name__}") from exc
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

    # -- public API --------------------------------------------------------
    def get(self, env_key: str) -> str | None:
        if self.backend_name == "keyring":
            try:
                return self._kr().get_password(SERVICE, env_key)
            except Exception as exc:
                raise SecretStoreError(f"Keyring read failed: {exc.__class__.__name__}") from exc
        if self.backend_name == "file":
            return self._read_file().get(env_key)
        return self._session.get(env_key)

    def set(self, env_key: str, value: str) -> None:
        if not value:
            raise SecretStoreError("Refusing to store an empty secret.")
        if self.backend_name == "keyring":
            try:
                self._kr().set_password(SERVICE, env_key, value)
            except Exception as exc:
                raise SecretStoreError(f"Keyring write failed: {exc.__class__.__name__}") from exc
        elif self.backend_name == "file":
            data = self._read_file()
            data[env_key] = value
            self._write_file(data)
        else:
            self._session[env_key] = value

    def delete(self, env_key: str) -> bool:
        if self.backend_name == "keyring":
            kr = self._kr()
            try:
                if kr.get_password(SERVICE, env_key) is None:
                    return False
                kr.delete_password(SERVICE, env_key)
                return True
            except Exception as exc:
                raise SecretStoreError(f"Keyring delete failed: {exc.__class__.__name__}") from exc
        if self.backend_name == "file":
            data = self._read_file()
            if env_key not in data:
                return False
            del data[env_key]
            self._write_file(data)
            return True
        return self._session.pop(env_key, None) is not None
