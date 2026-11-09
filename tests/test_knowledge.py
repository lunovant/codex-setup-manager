from codex_setup.diagnostics.knowledge import ISSUES, lookup

EXPECTED = {"provider_mismatch", "windows_setup", "sandbox_status", "unable_to_send", "unauthorized",
            "forbidden", "model_not_found", "rate_limited", "responses_incompatible", "invalid_config",
            "env_missing", "codex_not_found"}


def ids(text):
    return {i.id for i in lookup(text)}


def test_all_issues_bilingual():
    assert {i.id for i in ISSUES} == EXPECTED
    for i in ISSUES:
        for d in (i.title, i.explanation):
            assert d["en"] and d["vi"]
        assert i.steps["en"] and i.steps["vi"]
        assert any(ord(c) > 127 for c in i.explanation["vi"])


def test_lookups():
    assert "provider_mismatch" in ids("Model provider mismatch for thread")
    assert "windows_setup" in ids("Couldn't check Windows setup")
    assert "sandbox_status" in ids("Couldn't check agent sandbox status")
    assert "unable_to_send" in ids("Unable to send message")
    assert "model_not_found" in ids("HTTP 404: model not found")
    assert "codex_not_found" in ids("zsh: codex: command not found")
    assert "codex_not_found" in ids("'codex' is not recognized as an internal or external command")
    assert "env_missing" in ids("Missing environment variable: LUNOVANT_API_KEY")
    assert "invalid_config" in ids("error parsing config.toml: invalid")
    assert lookup("") == [] and lookup("totally unrelated") == []


def test_windows_messages_guidance():
    for iid in ("windows_setup", "sandbox_status", "unable_to_send"):
        issue = next(i for i in ISSUES if i.id == iid)
        for lang in ("en", "vi"):
            text = " ".join(issue.steps[lang]) + issue.explanation[lang]
            assert "unelevated" in text
    for iid in ("windows_setup", "sandbox_status"):
        issue = next(i for i in ISSUES if i.id == iid)
        assert "never disables" in " ".join(issue.steps["en"])
        assert "elevated" in issue.explanation["en"]


def test_provider_mismatch_text():
    i = next(i for i in ISSUES if i.id == "provider_mismatch")
    assert "new thread" in " ".join(i.steps["en"]).lower()
