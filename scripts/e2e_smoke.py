#!/usr/bin/env python3
"""End-to-end smoke test for a built lunovant-setup binary (stdlib only).

Usage:
    python scripts/e2e_smoke.py <path-to-binary> [--with-codex]
    python scripts/e2e_smoke.py --cmd "<python> -m codex_setup" [--with-codex]

Starts a fake Lunovant server, runs the real one-click flow against it in an
isolated HOME, checks the written config and (optionally) that the real Codex
CLI accepts it.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KEY = "sk-ci-e2e-0123456789abcdef"
PROBE_EXCLUDED = ("gpt-image-2", "codex-auto-review")

USAGE = {
    "isValid": True,
    "status": "active",
    "planName": "CI",
    "remaining": 42.5,
    "expires_at": None,
}
MODELS = {
    "data": [
        {"id": "gpt-6.1-sol"},
        {"id": "gpt-6.2-sol"},
        {"id": "gpt-image-2"},
        {"id": "codex-auto-review"},
    ]
}
RESPONSE = {
    "id": "resp_ci",
    "object": "response",
    "status": "completed",
    "output": [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "OK"}],
        }
    ],
    "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
}


class FakeServer:
    """Fake Lunovant API recording every request."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:  # silence
                pass

            def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _record(self, body: bytes = b"") -> None:
                with outer._lock:
                    outer.requests.append(
                        {
                            "method": self.command,
                            "path": self.path,
                            "auth": self.headers.get("Authorization", ""),
                            "body": body.decode("utf-8", "replace"),
                        }
                    )

            def do_GET(self) -> None:
                self._record()
                path = self.path.split("?")[0]
                if path == "/v1/usage":
                    self._send(200, json.dumps(USAGE).encode())
                elif path == "/v1/models":
                    self._send(200, json.dumps(MODELS).encode())
                else:
                    self._send(404, b'{"error":"not found"}')

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                self._record(body)
                if self.path.split("?")[0] != "/v1/responses":
                    self._send(404, b'{"error":"not found"}')
                    return
                try:
                    stream = bool(json.loads(body or b"{}").get("stream"))
                except (ValueError, AttributeError):
                    stream = False
                if not stream:
                    self._send(200, json.dumps(RESPONSE).encode())
                    return
                created = {**RESPONSE, "status": "in_progress", "output": []}
                events = [
                    ("response.created", {"type": "response.created", "response": created}),
                    (
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "output_index": 0,
                            "item": {
                                "type": "message",
                                "id": "msg_ci",
                                "role": "assistant",
                                "content": [],
                            },
                        },
                    ),
                    (
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "item_id": "msg_ci",
                            "output_index": 0,
                            "content_index": 0,
                            "delta": "OK",
                        },
                    ),
                    (
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "output_index": 0,
                            "item": {**RESPONSE["output"][0], "id": "msg_ci"},
                        },
                    ),
                    ("response.completed", {"type": "response.completed", "response": RESPONSE}),
                ]
                payload = "".join(
                    f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events
                ).encode()
                self._send(200, payload, "text/event-stream")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self.requests)


class Results:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, bool(ok), "" if ok else detail))
        return bool(ok)

    def skip(self, name: str, detail: str) -> None:
        self.rows.append((name, True, f"SKIP: {detail}"))

    def table(self) -> str:
        width = max((len(n) for n, _, _ in self.rows), default=10)
        lines = []
        for name, ok, detail in self.rows:
            mark = "PASS" if ok and not detail.startswith("SKIP") else ("SKIP" if ok else "FAIL")
            lines.append(f"{mark}  {name.ljust(width)}  {detail}".rstrip())
        return "\n".join(lines)

    @property
    def failed(self) -> bool:
        return any(not ok for _, ok, _ in self.rows)


def isolated_env(tmp: Path, codex_home: Path) -> dict[str, str]:
    env = dict(os.environ)
    for k in ("OPENAI_API_KEY", "LUNOVANT_API_KEY", "CODEX_API_KEY"):
        env.pop(k, None)
    home = str(tmp)
    env.update(
        HOME=home,
        USERPROFILE=home,
        APPDATA=home,
        LOCALAPPDATA=home,
        XDG_CONFIG_HOME=home,
        CODEX_HOME=str(codex_home),
        PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
        NO_COLOR="1",
        PYTHONUTF8="1",
    )
    return env


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the process and all its descendants."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def run_tree(cmd, env: dict, stdin: str | None, timeout: int, **kwargs):
    """Run ``cmd`` in its own process group; on timeout kill the whole tree.

    Returns (returncode, stdout, stderr); returncode is 124 on timeout.
    """
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )
    try:
        out, err = proc.communicate(stdin, timeout=timeout)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return 124, out or "", (err or "") + "\n[timeout]"


def run(cmd: list[str], env: dict, stdin: str | None = None, timeout: int = 120):
    return run_tree(cmd, env, stdin, timeout)


def parse_cmd(text: str, windows: bool | None = None) -> list[str]:
    """Split a command line; on Windows strip the quotes around each token."""
    windows = (os.name == "nt") if windows is None else windows
    if not windows:
        return shlex.split(text)
    out = []
    for tok in shlex.split(text, posix=False):
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
            tok = tok[1:-1]
        out.append(tok)
    return out


def load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_flow(base_cmd: list[str], with_codex: bool, res: Results) -> None:
    server = FakeServer()
    tmp = Path(tempfile.mkdtemp(prefix="codex-e2e-"))
    try:
        server.start()
        codex_home = tmp / ".codex"
        codex_home.mkdir()
        env = isolated_env(tmp, codex_home)
        common = base_cmd + ["--lang", "en", "--yes", "--codex-home", str(codex_home)]

        # 3. one-click setup
        code, out, err = run(
            common + ["setup", "--auto", "--base-url", server.base_url, "--key-stdin"],
            env,
            stdin=KEY + "\n",
        )
        res.check("setup --auto exit 0", code == 0, f"exit={code}\n{out}\n{err}"[-1500:])
        cfg_path = codex_home / "config.toml"
        cfg = load_toml(cfg_path)
        res.check("model_provider = lunovant", cfg.get("model_provider") == "lunovant", str(cfg.get("model_provider")))
        prov = cfg.get("model_providers", {}).get("lunovant", {})
        res.check("provider base_url", prov.get("base_url") == server.base_url, str(prov.get("base_url")))
        res.check("bearer token = key", prov.get("experimental_bearer_token") == KEY, "token mismatch")
        res.check("no env_key", "env_key" not in prov, str(prov.get("env_key")))
        res.check("lunovant.config.toml exists", (codex_home / "lunovant.config.toml").exists(), "missing")

        reqs = server.snapshot()
        res.check("server received requests", len(reqs) > 0, "none")
        probed = [
            r for r in reqs if r["method"] == "POST" and any(m in r["body"] for m in PROBE_EXCLUDED)
        ]
        res.check("image/auto-review not probed", not probed, str([r["body"][:80] for r in probed]))
        bad = [r for r in reqs if r["auth"] != f"Bearer {KEY}"]
        res.check("all requests carry Bearer key", not bad, str([(r["method"], r["path"]) for r in bad]))
        res.check("key not in stdout/stderr", KEY not in out and KEY not in err, "key leaked")

        # 4. mode switching
        (codex_home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")
        code, out, err = run(common + ["mode", "personal"], env)
        cfg = load_toml(cfg_path)
        res.check("mode personal", code == 0 and "model_provider" not in cfg, f"exit={code} {out}{err}"[-800:])
        code, out, err = run(common + ["mode", "lunovant"], env)
        cfg = load_toml(cfg_path)
        res.check(
            "mode lunovant",
            code == 0 and cfg.get("model_provider") == "lunovant",
            f"exit={code} {out}{err}"[-800:],
        )
        code, out, err = run(common + ["mode"], env)
        res.check("mode prints current", code == 0 and "lunovant" in (out + err).lower(), f"exit={code} {out}{err}"[-800:])

        # 5. real Codex CLI
        if with_codex:
            run_codex(server, codex_home, env, res)
    finally:
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


def check_catalog(codex: str, codex_home: Path, env: dict, res: Results) -> None:
    """The model catalog file exists and the real Codex lists the sold models through it."""
    catalog = codex_home / "lunovant-models.json"
    res.check("lunovant-models.json exists", catalog.is_file(), "missing")
    if not catalog.is_file():
        return
    res.check("catalog has no key", KEY not in catalog.read_text(encoding="utf-8"), "key leaked")
    prof = load_toml(codex_home / "lunovant.config.toml")
    res.check("profile file points at the catalog",
              prof.get("model_catalog_json") == str(catalog), str(prof.get("model_catalog_json")))
    # `debug models` takes no --profile: mode is lunovant here, so config.toml's top level applies
    cmd = [codex, "debug", "models"]
    if os.name == "nt":
        cmd = subprocess.list2cmdline(cmd)  # type: ignore[assignment]
    try:
        code, out, err = run_tree(
            cmd, env, None, 60, shell=(os.name == "nt"), cwd=str(codex_home.parent)
        )
        slugs = [m.get("slug") for m in json.loads(out).get("models", []) if m.get("visibility") == "list"]
    except (OSError, ValueError) as exc:
        res.check("codex debug models", False, str(exc))
        return
    res.check("codex debug models exit 0", code == 0, f"exit={code}\n{out[-300:]}\n{err}"[-1000:])
    res.check("catalog lists gpt-6.2-sol", "gpt-6.2-sol" in slugs, str(slugs))
    res.check("catalog hides unsold models", "gpt-5.5" not in slugs, str(slugs))


def run_codex(server: FakeServer, codex_home: Path, env: dict, res: Results) -> None:
    codex = shutil.which("codex")
    if not codex:
        res.skip("codex exec", "`codex` not found on PATH")
        return
    check_catalog(codex, codex_home, env, res)
    before = len(server.snapshot())
    cmd = [codex, "exec", "--skip-git-repo-check", "-p", "lunovant", "hi"]
    if os.name == "nt":
        cmd = subprocess.list2cmdline(cmd)  # type: ignore[assignment]
    try:
        code, out, err = run_tree(
            cmd, env, None, 120, shell=(os.name == "nt"), cwd=str(codex_home.parent)
        )
    except OSError as exc:
        res.check("codex exec runs", False, str(exc))
        return
    new = server.snapshot()[before:]
    hit = [
        r for r in new
        if r["method"] == "POST" and r["path"].split("?")[0] == "/v1/responses" and r["auth"] == f"Bearer {KEY}"
    ]
    res.check("codex exec exit 0", code == 0, f"exit={code}\n{out}\n{err}"[-1500:])
    res.check("codex POST /v1/responses with key", bool(hit), f"requests={[(r['method'], r['path']) for r in new]}")
    res.check("codex printed OK", "OK" in out, f"stdout={out[-300:]!r} stderr={err[-500:]!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("binary", nargs="?", help="path to the built binary")
    ap.add_argument("--cmd", help='command prefix instead of a binary, e.g. "python -m codex_setup"')
    ap.add_argument("--with-codex", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd:
        base_cmd = parse_cmd(args.cmd)
    elif args.binary:
        base_cmd = [str(Path(args.binary).resolve())]
    else:
        ap.error("give a binary path or --cmd")
    base_cmd[0] = shutil.which(base_cmd[0]) or str(Path(base_cmd[0]).resolve())

    res = Results()
    try:
        run_flow(base_cmd, args.with_codex, res)
    except Exception as exc:  # noqa: BLE001
        res.check("e2e flow", False, f"{type(exc).__name__}: {exc}")
    print(res.table())
    print("RESULT:", "FAIL" if res.failed else "PASS")
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main())
