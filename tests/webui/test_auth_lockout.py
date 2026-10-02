"""Login brute-force protection and password comparison."""
import pytest

from webui import auth, config


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(auth, "_failures", {})
    monkeypatch.setattr(auth, "_locked_until", {})
    monkeypatch.setattr(config, "WEBUI_PASSWORD", "correct horse")


def test_non_ascii_password_is_a_plain_mismatch_not_an_error():
    assert auth.check_password("pässwörd") is False
    assert auth.check_password("correct horse") is True


def test_client_locked_after_repeated_failures():
    for i in range(auth.PER_CLIENT_MAX_FAILURES):
        assert auth.lockout_remaining("1.2.3.4", now=1000 + i) == 0
        auth.record_failure("1.2.3.4", now=1000 + i)
    assert auth.lockout_remaining("1.2.3.4", now=1010) > 0
    assert auth.lockout_remaining("5.6.7.8", now=1010) == 0
    assert auth.lockout_remaining("1.2.3.4", now=1010 + auth.LOCKOUT_SECS) == 0


def test_distributed_guessing_triggers_global_lockout():
    for i in range(auth.GLOBAL_MAX_FAILURES):
        auth.record_failure(f"10.0.0.{i}", now=2000 + i)
    assert auth.lockout_remaining("10.9.9.9", now=2100) > 0


def test_cloudflare_header_identifies_the_client():
    class Req:
        headers = {"cf-connecting-ip": "203.0.113.7"}
        client = type("C", (), {"host": "127.0.0.1"})()
    assert auth.client_id(Req()) == "203.0.113.7"
