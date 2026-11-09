#!/usr/bin/env python3
"""Build a one-file PyInstaller executable for the current OS/arch only.

Usage:
    python scripts/build.py [--smoke] [--skip-build]
                            [--codesign-identity NAME] [--entitlements PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "scripts" / "entry.py"
SRC = ROOT / "src"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
DEFAULT_ENTITLEMENTS = ROOT / "scripts" / "entitlements.plist"

HIDDEN_IMPORTS = (
    "keyring.backends.macOS",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
    "keyring.backends.chainer",
    "keyring.backends.fail",
    "keyring.backends.null",
    "jaraco.classes",
    "jaraco.functools",
    "jaraco.context",
)

COLLECT_SUBMODULES = ("keyring", "rich._unicode_data", "codex_setup")


def exe_name() -> str:
    """Return the output file name for the current platform."""
    machine = platform.machine().lower()
    arch_map = {
        "amd64": "x64",
        "x86_64": "x64",
        "x64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    arch = arch_map.get(machine, machine or "unknown")
    if sys.platform.startswith("win"):
        os_name = "windows"
    elif sys.platform == "darwin":
        os_name = "macos"
    elif sys.platform.startswith("linux"):
        os_name = "linux"
    else:
        os_name = sys.platform
    name = f"codex-setup-{os_name}-{arch}"
    return name + ".exe" if os_name == "windows" else name


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def build_command(name: str, identity: str | None = None, entitlements: Path | None = None) -> list[str]:
    stem = name[:-4] if name.endswith(".exe") else name
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--name",
        stem,
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        "--specpath",
        str(BUILD),
        "--paths",
        str(SRC),
    ]
    for mod in COLLECT_SUBMODULES:
        if _module_exists(mod):
            cmd += ["--collect-submodules", mod]
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]
    if identity:
        # Onefile embedded binaries can only be signed during the build itself.
        cmd += ["--codesign-identity", identity]
        if entitlements:
            cmd += ["--osx-entitlements-file", str(entitlements)]
    cmd.append(str(ENTRY))
    return cmd


def codesign(exe: Path, identity: str, entitlements: Path) -> None:
    """Re-sign the final executable (hardened runtime) and verify it."""
    sign = ["codesign", "--force"]
    if identity != "-":
        sign.append("--timestamp")
    sign += ["--options", "runtime", "--entitlements", str(entitlements), "--sign", identity, str(exe)]
    subprocess.run(sign, check=True)
    subprocess.run(["codesign", "--verify", "--strict", "--verbose=2", str(exe)], check=True)
    info = subprocess.run(["codesign", "-dv", str(exe)], capture_output=True, text=True, check=True)
    for line in (info.stdout + info.stderr).splitlines():
        if line.startswith(("Authority=", "TeamIdentifier=")):
            print(line)


def write_sha256(path: Path) -> Path:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    out = path.with_name(path.name + ".sha256")
    out.write_text(f"{digest.hexdigest()}  {path.name}\n", encoding="utf-8")
    return out


def smoke(exe: Path) -> None:
    for args in (["--version"], ["status", "--help"]):
        print(f"[smoke] {exe.name} {' '.join(args)}", flush=True)
        proc = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout + proc.stderr)
            raise SystemExit(f"smoke test failed ({' '.join(args)}): exit {proc.returncode}")
        print((proc.stdout or proc.stderr).strip().splitlines()[0] if (proc.stdout or proc.stderr).strip() else "(no output)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Codex Setup Manager executable for this OS/arch.")
    parser.add_argument("--smoke", action="store_true", help="run '--version' and 'status --help' on the built binary")
    parser.add_argument("--skip-build", action="store_true", help="skip PyInstaller (only checksum/smoke an existing binary)")
    parser.add_argument(
        "--codesign-identity",
        default=os.environ.get("MACOS_SIGN_IDENTITY") or None,
        help="macOS signing identity ('-' for ad-hoc); default: env MACOS_SIGN_IDENTITY; ignored off macOS",
    )
    parser.add_argument(
        "--entitlements",
        type=Path,
        default=None,
        help="entitlements plist (default: scripts/entitlements.plist when signing)",
    )
    args = parser.parse_args(argv)

    identity = args.codesign_identity if sys.platform == "darwin" else None
    entitlements = (args.entitlements or DEFAULT_ENTITLEMENTS) if identity else None
    if entitlements and not entitlements.is_file():
        raise SystemExit(f"entitlements file not found: {entitlements}")

    name = exe_name()
    target = DIST / name
    if not args.skip_build:
        DIST.mkdir(parents=True, exist_ok=True)
        subprocess.run(build_command(name, identity, entitlements), cwd=ROOT, check=True)
    if not target.is_file():
        raise SystemExit(f"expected build output not found: {target}")
    if not sys.platform.startswith("win"):
        target.chmod(target.stat().st_mode | 0o111)
    if identity and entitlements:
        codesign(target, identity, entitlements)
    checksum = write_sha256(target)
    print(f"built: {target}\nsha256 file: {checksum}")
    if args.smoke:
        smoke(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
