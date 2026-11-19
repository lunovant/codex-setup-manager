"""Runs scripts/e2e_smoke.py against the source entry point (no Codex CLI)."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "e2e_smoke.py"


def test_e2e_smoke_against_source():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--cmd", f'"{sys.executable}" -m codex_setup'],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RESULT: PASS" in proc.stdout


def _load():
    import importlib.util

    spec = importlib.util.spec_from_file_location("e2e_smoke", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_cmd_strips_windows_quotes():
    mod = _load()
    got = mod.parse_cmd(r'"C:\Program Files\Python 312\python.exe" -m codex_setup', windows=True)
    assert got == [r"C:\Program Files\Python 312\python.exe", "-m", "codex_setup"]
    assert mod.parse_cmd('"/a b/python" -m x', windows=False) == ["/a b/python", "-m", "x"]


def test_timeout_kills_process_tree():
    import os
    import time

    mod = _load()
    code = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "time.sleep(60)"
    )
    start = time.monotonic()
    rc, _out, err = mod.run_tree([sys.executable, "-c", code], dict(os.environ), None, 2)
    assert rc == 124 and "[timeout]" in err
    assert time.monotonic() - start < 30
