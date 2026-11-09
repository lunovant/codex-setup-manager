from codex_setup.security.redact import mask_key, redact


def test_mask_key():
    assert mask_key(None) == "(not set)"
    assert mask_key("") == "(not set)"
    assert mask_key("12345678") == "****"
    assert mask_key("sk-test-SECRET-1234567890") == "sk-…7890"


def test_redact_secrets_and_bearer():
    key = "sk-test-SECRET-1234567890"
    out = redact(f"key={key} and Authorization: Bearer abcdefghijkl123456", [key, "", "ab"])
    assert key not in out
    assert "abcdefghijkl123456" not in out
    assert "sk-…7890" in out


def test_redact_short_secret_ignored():
    assert redact("abc here", ["abc"]) == "abc here"
