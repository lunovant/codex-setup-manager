import socket
import ssl

import httpx
import pytest

from codex_setup.diagnostics.api_test import Outcome, Problem, run_api_test

KEY = "sk-test-SECRET-1234567890"
BASE = "https://api.example.com/v1"
OK_BODY = {"object": "response", "output": [{"type": "message"}]}
SSE = ("event: response.created\ndata: {\"type\":\"response.created\"}\n\n"
       "event: response.completed\ndata: {\"type\":\"response.completed\"}\n\n")


def echo(status, extra=""):
    def h(req):
        return httpx.Response(status, text=f"err auth={req.headers.get('authorization')} key={KEY} {extra}")
    return h


def make_handler(*, root=None, models=None, responses=None, stream=None):
    def handler(req: httpx.Request):
        path = req.url.path
        if path == "/":
            return (root or (lambda r: httpx.Response(200, text="hi")))(req)
        if path.endswith("/models"):
            return (models or (lambda r: httpx.Response(200, json={"data": [{"id": "m1"}]})))(req)
        if path.endswith("/responses"):
            import json as _j
            is_stream = _j.loads(req.content).get("stream")
            if is_stream:
                return (stream or (lambda r: httpx.Response(200, text=SSE)))(req)
            return (responses or (lambda r: httpx.Response(200, json=OK_BODY)))(req)
        return httpx.Response(404)
    return handler


def run(handler, model="m1", base=BASE):
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        return run_api_test(base, KEY, model, client=c)


def step(rep, name):
    return next(s for s in rep.steps if s.step == name)


def test_success():
    rep = run(make_handler())
    assert rep.overall == Outcome.OK
    assert all(s.outcome == Outcome.OK for s in rep.steps)


def test_non_stream_ok_stream_bad_not_ok():
    rep = run(make_handler(stream=lambda r: httpx.Response(200, text="event: response.created\ndata: {}\n\n")))
    assert step(rep, "responses_stream").problem == Problem.INCOMPATIBLE
    assert rep.overall == Outcome.FAIL


def test_401_and_403():
    rep = run(make_handler(models=echo(401)))
    assert step(rep, "models").problem == Problem.UNAUTHORIZED
    assert step(rep, "responses").outcome == Outcome.SKIP and rep.overall == Outcome.FAIL
    rep = run(make_handler(models=echo(403)))
    assert step(rep, "models").problem == Problem.FORBIDDEN


def test_models_404_warns_and_continues():
    rep = run(make_handler(models=lambda r: httpx.Response(404)))
    assert step(rep, "models").outcome == Outcome.WARN
    assert "/v1" in step(rep, "models").detail
    assert step(rep, "model_listed").outcome == Outcome.SKIP
    assert step(rep, "responses").outcome == Outcome.OK
    assert rep.overall == Outcome.OK or rep.overall == Outcome.WARN


def test_models_html():
    rep = run(make_handler(models=lambda r: httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})))
    s = step(rep, "models")
    assert s.problem == Problem.BAD_URL and s.outcome == Outcome.FAIL and "/v1" in s.detail
    assert rep.overall == Outcome.FAIL


def test_model_not_listed():
    rep = run(make_handler(), model="other")
    assert step(rep, "model_listed").outcome == Outcome.WARN


def test_responses_404_model():
    rep = run(make_handler(responses=lambda r: httpx.Response(404, json={"error": "The model `m1` does not exist"}),
                           stream=lambda r: httpx.Response(404, text="model m1 not found")))
    assert step(rep, "responses").problem == Problem.MODEL_NOT_FOUND


@pytest.mark.parametrize("status", [404, 405])
def test_responses_unsupported(status):
    rep = run(make_handler(responses=lambda r: httpx.Response(status, text="nope"),
                           stream=lambda r: httpx.Response(status, text="nope")))
    assert step(rep, "responses").problem == Problem.RESPONSES_UNSUPPORTED


def test_429_500():
    rep = run(make_handler(responses=lambda r: httpx.Response(429, text="slow")))
    assert step(rep, "responses").problem == Problem.RATE_LIMITED
    rep = run(make_handler(responses=lambda r: httpx.Response(500, text="boom")))
    assert step(rep, "responses").problem == Problem.SERVER_ERROR


def test_2xx_incompatible():
    rep = run(make_handler(responses=lambda r: httpx.Response(200, json={"hello": 1})))
    assert step(rep, "responses").problem == Problem.INCOMPATIBLE
    assert rep.overall == Outcome.FAIL


def test_only_models_succeeds_not_ok():
    rep = run(make_handler(responses=lambda r: httpx.Response(500, text="x"),
                           stream=lambda r: httpx.Response(500, text="x")))
    assert rep.overall != Outcome.OK


def raiser(exc):
    def h(req):
        raise exc
    return h


def test_timeouts():
    for exc in (httpx.ConnectTimeout("t"), httpx.ReadTimeout("t")):
        rep = run(make_handler(root=raiser(exc)))
        assert step(rep, "connect").problem == Problem.TIMEOUT
    rep = run(make_handler(models=raiser(httpx.ReadTimeout("t"))))
    assert step(rep, "models").problem == Problem.TIMEOUT


def test_dns_and_tls_network():
    err = httpx.ConnectError("[Errno 8] failed")
    err.__cause__ = socket.gaierror(8, "nodename nor servname provided")
    assert step(run(make_handler(root=raiser(err))), "connect").problem == Problem.DNS
    err = httpx.ConnectError("[Errno -2] Name or service not known")
    assert step(run(make_handler(root=raiser(err))), "connect").problem == Problem.DNS
    err = httpx.ConnectError("bad cert")
    err.__cause__ = ssl.SSLCertVerificationError("verify failed")
    assert step(run(make_handler(root=raiser(err))), "connect").problem == Problem.TLS
    assert step(run(make_handler(root=raiser(httpx.ConnectError("refused")))), "connect").problem == Problem.NETWORK


def test_bad_url():
    for base in ("not a url", "ftp://x/v1", ""):
        rep = run(make_handler(), base=base)
        assert step(rep, "connect").problem == Problem.BAD_URL and rep.overall == Outcome.FAIL


SCENARIOS = {
    "ok": make_handler(),
    "401": make_handler(models=echo(401)),
    "403": make_handler(models=echo(403)),
    "html": make_handler(models=lambda r: httpx.Response(200, text=f"<html>{KEY}</html>")),
    "404models": make_handler(models=echo(404)),
    "resp404": make_handler(responses=echo(404, "model"), stream=echo(404, "model")),
    "resp405": make_handler(responses=echo(405), stream=echo(405)),
    "429": make_handler(responses=echo(429), stream=echo(429)),
    "500": make_handler(responses=echo(500), stream=echo(500)),
    "incompat": make_handler(responses=lambda r: httpx.Response(200, text=f"{KEY} not json")),
    "nostream": make_handler(stream=lambda r: httpx.Response(200, text=f"data: {KEY}\n\n")),
    "timeout": make_handler(root=raiser(httpx.ConnectTimeout(f"t {KEY}"))),
    "net": make_handler(root=raiser(httpx.ConnectError(f"boom {KEY}"))),
    "tls": make_handler(models=raiser(httpx.ConnectError(f"tls {KEY}"))),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_no_key_leak(name):
    rep = run(SCENARIOS[name])
    assert KEY not in repr(rep)
    for s in rep.steps:
        assert KEY not in repr(s) and KEY not in s.detail
