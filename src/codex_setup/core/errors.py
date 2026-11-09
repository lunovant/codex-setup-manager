"""Exception hierarchy for Codex Setup Manager."""

from __future__ import annotations

from pathlib import Path


class CodexSetupError(Exception):
    """Base class for all tool errors."""


class ConfigParseError(CodexSetupError):
    def __init__(
        self,
        message: str,
        path: Path | None = None,
        line: int | None = None,
        col: int | None = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.line = line
        self.col = col


class ConfigWriteError(CodexSetupError):
    """Raised after a rollback was attempted."""

    def __init__(self, message: str, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path


class ReservedProviderError(CodexSetupError):
    pass


class SecretStoreError(CodexSetupError):
    pass


class ValidationError(CodexSetupError):
    """Bad URL / id / env var name / model name."""
