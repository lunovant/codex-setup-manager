"""Step-by-step connection test for an OpenAI-compatible Responses API."""

from __future__ import annotations

import json
import socket
import ssl
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit

import httpx

from codex_setup.security.redact import redact


class Outcome(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class Problem(StrEnum):
    BAD_URL = "bad_url"
    DNS = "dns"
    TLS = "tls"
    NETWORK = "network"
    TIMEOUT = "timeout"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    MODEL_NOT_FOUND = "model_not_found"
    RATE_LIMITED = "rate_limited"
    RESPONSES_UNSUPPORTED = "responses_unsupported"
    SERVER_ERROR = "server_error"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


@dataclass
class StepResult:
    step: str
    outcome: Outcome
    problem: Problem | None
    detail: str  # English, for logs/tests
    http_status: int | None = None
    code: str | None = None  # stable i18n key (``at_*``) used by the presentation layer
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class ApiTestReport:
    steps: list[StepResult] = field(default_factory=list)
    overall: Outcome = Outcome.WARN


MAX_STREAM_BYTES = 2 * 1024 * 1024
_START_EVENTS = {"response.created", "response.in_progress", "response.output_text.delta"}
_DONE_EVENTS = {"response.completed", "response.done"}
_ERROR_EVENTS = {"error", "response.failed", "response.incomplete"}

_STEPS = ("connect", "models", "model_listed", "responses", "responses_stream")
_DNS_MARKERS = ("name or service not known", "nodename nor servname", "getaddrinfo failed",
                "temporary failure in name resolution", "no address associated")


def _snippet(text: str, key: str) -> str:
    return redact(text, [key])[:300]


def _chain(exc: BaseException):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def classify_transport(exc: Exception, key: str) -> tuple[Problem, str]:
    if isinstance(exc, (httpx.InvalidURL, httpx.UnsupportedProtocol)):
        return Problem.BAD_URL, _snippet(f"Invalid URL: {exc}", key)
    if isinstance(exc, httpx.TimeoutException):
        return Problem.TIMEOUT, f"Timed out ({exc.__class__.__name__})."
    chain = list(_chain(exc))
    if any(isinstance(e, ssl.SSLError) for e in chain):
        return Problem.TLS, _snippet(f"TLS/certificate error: {exc}", key)
    if any(isinstance(e, socket.gaierror) for e in chain) or any(
        m in str(e).lower() for e in chain for m in _DNS_MARKERS
    ):
        return Problem.DNS, "DNS lookup failed: the host name could not be resolved."
    return Problem.NETWORK, _snippet(f"Network error: {exc}", key)


def _status_problem(status: int) -> tuple[Problem, str] | None:
    if status == 401:
        return Problem.UNAUTHORIZED, "401 Unauthorized: the API key was rejected."
    if status == 403:
        return Problem.FORBIDDEN, "403 Forbidden: the key has no access."
    if status == 429:
        return Problem.RATE_LIMITED, "429 Too Many Requests: rate limited or out of quota."
    if status >= 500:
        return Problem.SERVER_ERROR, f"{status}: server error on the provider side."
    return None


def _is_json(resp: httpx.Response) -> object | None:
    try:
        return resp.json()
    except ValueError:
        return None


def _looks_like_response(data: object) -> bool:
    return isinstance(data, dict) and (
        "output" in data or "output_text" in data or data.get("object") == "response"
    )


@dataclass
class StreamVerdict:
    outcome: Outcome
    problem: Problem | None
    detail: str
    code: str
    params: dict[str, str] = field(default_factory=dict)


def _event_message(obj: object) -> str:
    if isinstance(obj, dict):
        for source in (obj, obj.get("response")):
            if isinstance(source, dict):
                err = source.get("error")
                if isinstance(err, dict) and err.get("message"):
                    return str(err["message"])
                if isinstance(err, str):
                    return err
                if source.get("message"):
                    return str(source["message"])
                details = source.get("incomplete_details")
                if isinstance(details, dict) and details.get("reason"):
                    return str(details["reason"])
    return ""


def check_sse_stream(
    lines: Iterable[str],
    api_key: str,
    *,
    deadline: float,
    max_bytes: int = MAX_STREAM_BYTES,
    clock=time.monotonic,
) -> StreamVerdict:
    """Parse SSE records (event/data lines, blank-line terminated) and judge the stream.

    ``deadline`` is an absolute ``clock()`` value. Stops right after a terminal event.
    """
    started = False
    total = 0
    event: str | None = None
    data: list[str] = []

    def fail(detail: str, code: str, problem: Problem = Problem.INCOMPATIBLE, **params: str):
        return StreamVerdict(Outcome.FAIL, problem, _snippet(detail, api_key), code, params)

    def dispatch() -> StreamVerdict | None:
        nonlocal started, event, data
        name, payload, event, data = event, "\n".join(data), None, []
        if not payload and not name:
            return None
        if payload.strip() == "[DONE]":
            return None
        obj: object = None
        if payload:
            try:
                obj = json.loads(payload)
            except ValueError:
                if name in _ERROR_EVENTS:
                    return fail(f"Stream error event: {payload}", "at_stream_error", message=_snippet(payload, api_key))
                return fail("Stream event data is not valid JSON.", "at_stream_bad_json")
        kind = obj.get("type") if isinstance(obj, dict) else None
        kind = kind if isinstance(kind, str) and kind else name
        if kind in _ERROR_EVENTS:
            msg = _snippet(_event_message(obj) or kind, api_key)
            return fail(f"Stream reported {kind}: {msg}", "at_stream_error", message=msg)
        if kind in _START_EVENTS:
            started = True
            return None
        if kind in _DONE_EVENTS:
            if not started:
                return fail(
                    "response.completed arrived before any start event "
                    "(response.created / response.in_progress / response.output_text.delta).",
                    "at_stream_no_start",
                )
            return StreamVerdict(Outcome.OK, None, "Streaming works.", "at_stream_ok")
        return None

    for raw in lines:
        if clock() > deadline:
            return StreamVerdict(
                Outcome.FAIL, Problem.TIMEOUT, "Streaming did not finish before the deadline.",
                "at_stream_deadline",
            )
        total += len(raw.encode("utf-8", "replace")) + 1
        if total > max_bytes:
            return fail("Streaming response exceeded the 2 MiB limit.", "at_stream_too_big")
        line = raw.rstrip("\r")
        if line == "":
            verdict = dispatch()
            if verdict is not None:
                return verdict
        elif line.startswith(":"):
            continue  # comment / heartbeat
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    verdict = dispatch()  # stream ended without a trailing blank line
    if verdict is not None:
        return verdict
    return fail(
        "Streaming response did not finish with response.completed "
        "(Codex requires streaming Responses).",
        "at_stream_incomplete",
    )


def run_api_test(
    base_url: str,
    api_key: str,
    model: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = 30.0,
    stream_deadline: float | None = None,
) -> ApiTestReport:
    steps: list[StepResult] = []

    def add(step, outcome, problem, detail, status=None, code=None, **params):
        if code is None:
            code = f"at_{problem.value}" if problem else None
        steps.append(StepResult(step, outcome, problem, detail, status, code,
                                {k: str(v) for k, v in params.items()}))
        return outcome

    def finish() -> ApiTestReport:
        done = {s.step for s in steps}
        for name in _STEPS:
            if name not in done:
                steps.append(StepResult(name, Outcome.SKIP, None, "Skipped.", code="at_skipped"))
        order = {n: i for i, n in enumerate(_STEPS)}
        steps.sort(key=lambda s: order[s.step])
        by = {s.step: s for s in steps}
        if any(s.outcome == Outcome.FAIL for s in steps):
            overall = Outcome.FAIL
        elif by["responses"].outcome == Outcome.OK and by["responses_stream"].outcome == Outcome.OK:
            overall = Outcome.OK
        else:
            overall = Outcome.WARN
        return ApiTestReport(steps=steps, overall=overall)

    base = (base_url or "").strip().rstrip("/")
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.netloc or not parts.hostname:
        add("connect", Outcome.FAIL, Problem.BAD_URL,
            "The base URL must start with http:// or https:// and include a host.",
            code="at_bad_url_scheme")
        return finish()
    origin = f"{parts.scheme}://{parts.netloc}/"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    own = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        # 1. connect
        try:
            r = http.get(origin)
            add("connect", Outcome.OK, None, f"Reachable (HTTP {r.status_code}).", r.status_code,
                code="at_connect_ok", http=r.status_code)
        except httpx.HTTPError as exc:
            prob, detail = classify_transport(exc, api_key)
            add("connect", Outcome.FAIL, prob, detail)
            return finish()
        except Exception as exc:  # e.g. ssl / invalid url raised by custom transports
            prob, detail = classify_transport(exc, api_key)
            add("connect", Outcome.FAIL, prob, detail)
            return finish()

        # 2. models
        models: list[str] | None = None
        try:
            r = http.get(f"{base}/models", headers=headers)
        except Exception as exc:
            prob, detail = classify_transport(exc, api_key)
            add("models", Outcome.FAIL, prob, detail)
            return finish()
        status = r.status_code
        sp = _status_problem(status) if status in (401, 403) else None
        if sp:
            add("models", Outcome.FAIL, sp[0], sp[1], status)
            return finish()
        if status == 404:
            add("models", Outcome.WARN, Problem.UNKNOWN,
                "GET /models returned 404 (endpoint missing). The base URL may need /v1.", status,
                code="at_models_404")
        elif 200 <= status < 300:
            data = _is_json(r)
            if data is None:
                add("models", Outcome.FAIL, Problem.BAD_URL,
                    "This looks like a web page, not an API. Try adding /v1 to the base URL.", status,
                    code="at_web_page")
                return finish()
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                models = [str(m.get("id")) for m in data["data"] if isinstance(m, dict)]
            add("models", Outcome.OK, None, f"Model list available ({len(models or [])} models).", status,
                code="at_models_ok", count=len(models or []))
        else:
            sp = _status_problem(status)
            add("models", Outcome.WARN, sp[0] if sp else Problem.UNKNOWN,
                _snippet(f"HTTP {status}: {r.text}", api_key), status,
                code=f"at_{sp[0].value}" if sp else "at_http_error", http=status)

        # 3. model_listed
        if models is None:
            add("model_listed", Outcome.SKIP, None, "Model list unavailable.", code="at_listed_skip")
        elif model in models:
            add("model_listed", Outcome.OK, None, f"Model {model} is listed.",
            code="at_listed_ok", model=model)
        else:
            add("model_listed", Outcome.WARN, Problem.MODEL_NOT_FOUND,
                f"Model {model} is not in the provider's model list.",
                code="at_listed_missing", model=model)

        body = {"model": model, "input": "Reply with OK", "max_output_tokens": 16}

        # 4. responses
        try:
            r = http.post(f"{base}/responses", headers=headers, json=body)
        except Exception as exc:
            prob, detail = classify_transport(exc, api_key)
            add("responses", Outcome.FAIL, prob, detail)
            return finish()
        status = r.status_code
        if 200 <= status < 300:
            if _looks_like_response(_is_json(r)):
                add("responses", Outcome.OK, None, "Responses API works.", status,
                    code="at_responses_ok")
            else:
                add("responses", Outcome.FAIL, Problem.INCOMPATIBLE,
                    _snippet(f"2xx but not a Responses API reply: {r.text}", api_key), status,
                    code="at_not_responses")
        else:
            p, d = _error_problem(status, r.text, model)
            add("responses", Outcome.FAIL, p, _snippet(d, api_key), status, http=status)

        # 5. responses_stream
        try:
            with http.stream("POST", f"{base}/responses", headers=headers,
                             json={**body, "stream": True}) as sr:
                status = sr.status_code
                if not 200 <= status < 300:
                    text = sr.read().decode("utf-8", "replace")
                    p, d = _error_problem(status, text, model)
                    add("responses_stream", Outcome.FAIL, p, _snippet(d, api_key), status, http=status)
                else:
                    limit = stream_deadline if stream_deadline is not None else timeout * 2
                    verdict = check_sse_stream(
                        sr.iter_lines(), api_key, deadline=time.monotonic() + limit
                    )
                    add("responses_stream", verdict.outcome, verdict.problem, verdict.detail,
                        status, verdict.code, **verdict.params)
        except Exception as exc:
            prob, detail = classify_transport(exc, api_key)
            add("responses_stream", Outcome.FAIL, prob, detail)
        return finish()
    finally:
        if own:
            http.close()


def _error_problem(status: int, text: str, model: str) -> tuple[Problem, str]:
    sp = _status_problem(status)
    if sp:
        return sp
    low = text.lower()
    if status in (404, 400) and (model.lower() in low or "model" in low):
        return Problem.MODEL_NOT_FOUND, f"HTTP {status}: model not found or unavailable. {text}"
    if status in (404, 405):
        return Problem.RESPONSES_UNSUPPORTED, f"HTTP {status}: /responses is not supported at this URL. {text}"
    return Problem.UNKNOWN, f"HTTP {status}: {text}"
