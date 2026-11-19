"""Key check, model listing and per-model probing for the one-click setup."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit

import httpx

from codex_setup.diagnostics.api_test import classify_transport, Problem
from codex_setup.security.redact import redact

INTERNAL_MODELS = frozenset({"codex-auto-review"})


def is_excluded_model(name: str) -> bool:
    """Internal and image models are not chat models Codex can use: never probe or offer them."""
    low = name.strip().lower()
    return low in INTERNAL_MODELS or "image" in low


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def parse_models(data: Any) -> list[str]:
    """Accept ``{data:[]}``, ``{models:[]}`` or a bare list; take ``id``/``name``; dedupe in order."""
    items: Any = data
    if isinstance(data, dict):
        items = data.get("data")
        if not isinstance(items, list):
            items = data.get("models")
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        name: Any = item
        if isinstance(item, dict):
            name = item.get("id") or item.get("name")
        if isinstance(name, str) and name.strip():
            name = name.strip()
            if not is_excluded_model(name) and name not in out:
                out.append(name)
    return out


def fetch_models(
    base_url: str, key: str, timeout: float = 30.0, *, client: httpx.Client | None = None
) -> list[str]:
    """Models this key may use (``GET {base}/models``). Empty list on any failure."""
    base = (base_url or "").strip().rstrip("/")
    own = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        r = http.get(f"{base}/models", headers=_headers(key))
        if not 200 <= r.status_code < 300:
            return []
        try:
            return parse_models(r.json())
        except ValueError:
            return []
    except Exception:
        return []
    finally:
        if own:
            http.close()


def _error_text(status: int) -> str:
    if status == 401:
        return "401 key không hợp lệ"
    if status == 403:
        return "403 key không có quyền"
    if status == 404:
        return "404 model không tồn tại"
    if status == 429:
        return "429 tạm hết lượt"
    if status >= 500:
        return f"{status} lỗi máy chủ"
    return f"HTTP {status}"


def _probe_one(http: httpx.Client, base: str, key: str, model: str) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "model": model, "ok": False, "latency_ms": None, "status_code": None, "error": None,
    }
    try:
        r = http.post(
            f"{base}/responses",
            headers=_headers(key),
            json={"model": model, "input": "Reply with OK", "max_output_tokens": 16},
        )
    except Exception as exc:
        problem, detail = classify_transport(exc, key)
        result["error"] = "timeout" if problem == Problem.TIMEOUT else redact(detail, [key])[:120]
        return result
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    result["status_code"] = r.status_code
    if 200 <= r.status_code < 300:
        result["ok"] = True
    else:
        result["error"] = _error_text(r.status_code)
    return result


def _probe_one_claude(http: httpx.Client, origin: str, key: str, model: str) -> dict[str, Any]:
    """One tiny ``POST {origin}/v1/messages`` (Anthropic wire format, both auth headers)."""
    started = time.monotonic()
    result: dict[str, Any] = {
        "model": model, "ok": False, "latency_ms": None, "status_code": None, "error": None,
        "tested": True,
    }
    try:
        r = http.post(
            f"{origin}/v1/messages",
            headers={
                "x-api-key": key,
                "Authorization": f"Bearer {key}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            # x-api-key is not stripped by httpx on a cross-origin redirect: never follow one
            follow_redirects=False,
            json={"model": model, "max_tokens": 8,
                  "messages": [{"role": "user", "content": "Reply with OK"}]},
        )
    except Exception as exc:
        problem, detail = classify_transport(exc, key)
        result["error"] = "timeout" if problem == Problem.TIMEOUT else redact(detail, [key])[:120]
        return result
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    result["status_code"] = r.status_code
    if 200 <= r.status_code < 300:
        result["ok"] = True
    else:
        result["error"] = _error_text(r.status_code)
    return result


def probe_claude_models(
    base_url: str,
    key: str,
    models: list[str],
    concurrency: int = 3,
    timeout: float = 30.0,
    *,
    client: httpx.Client | None = None,
    on_result: Any = None,
) -> list[dict[str, Any]]:
    """Probe exactly ``models`` (the ones we configure) through ``/v1/messages``."""
    parts = urlsplit((base_url or "").strip())
    origin = f"{parts.scheme}://{parts.netloc}"
    own = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def run(model: str) -> dict[str, Any]:
        res = _probe_one_claude(http, origin, key, model)
        if on_result is not None:
            try:
                on_result(res)
            except Exception:
                pass
        return res

    try:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            return list(pool.map(run, models))
    finally:
        if own:
            http.close()


def probe_models(
    base_url: str,
    key: str,
    models: list[str],
    concurrency: int = 3,
    timeout: float = 30.0,
    *,
    client: httpx.Client | None = None,
    on_result: Any = None,
) -> list[dict[str, Any]]:
    """One non-streaming /responses call per model; results keep the input order."""
    base = (base_url or "").strip().rstrip("/")
    own = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def run(model: str) -> dict[str, Any]:
        res = _probe_one(http, base, key, model)
        if on_result is not None:
            try:
                on_result(res)
            except Exception:
                pass
        return res

    try:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            return list(pool.map(run, models))
    finally:
        if own:
            http.close()


def check_key(
    base_url: str, key: str, timeout: float = 30.0, *, client: httpx.Client | None = None
) -> dict[str, Any]:
    """Key status from ``{origin}/v1/usage``."""
    parts = urlsplit((base_url or "").strip())
    url = f"{parts.scheme}://{parts.netloc}/v1/usage"
    info: dict[str, Any] = {
        "valid": False, "expired": False, "plan": None, "remaining": None,
        "expires_at": None, "days_left": None,
    }
    own = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        r = http.get(url, headers=_headers(key))
    except Exception:
        info["error"] = "network"
        return info
    finally:
        if own:
            http.close()
    if r.status_code in (401, 403):
        return info
    if not 200 <= r.status_code < 300:
        info["error"] = f"http_{r.status_code}"
        return info
    try:
        data = r.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        info["error"] = "bad_response"
        return info
    status = str(data.get("status") or "").lower()
    quota = data.get("quota") if isinstance(data.get("quota"), dict) else {}
    remaining = data.get("remaining")
    if remaining is None:
        remaining = quota.get("remaining")
    expires = data.get("expires_at")
    days = data.get("days_until_expiry")
    expired = status in ("expired", "disabled", "revoked") or (
        isinstance(days, (int, float)) and not isinstance(days, bool) and days < 0
    )
    if isinstance(expires, str) and expires and not expired:
        from datetime import datetime, timezone

        try:
            dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            expired = dt <= datetime.now(timezone.utc)
        except ValueError:
            pass
    info.update(
        valid=data.get("isValid") is not False or expired,
        expired=expired,
        plan=data.get("planName"),
        remaining=remaining,
        expires_at=expires,
        days_left=days,
    )
    return info
