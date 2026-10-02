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


def test_cloudflare_header_only_trusted_from_the_local_tunnel():
    from types import SimpleNamespace
    from webui import auth
    spoof = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"),
                            headers={"cf-connecting-ip": "198.51.100.1"})
    assert auth.client_id(spoof) == "203.0.113.9"
    tunnel = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"),
                             headers={"cf-connecting-ip": "198.51.100.1"})
    assert auth.client_id(tunnel) == "198.51.100.1"


def test_changing_the_password_ends_existing_sessions(monkeypatch):
    from webui import auth, config
    monkeypatch.setattr(config, "WEBUI_PASSWORD", "old")
    session = {"authenticated": True, "pw_fp": auth._password_fingerprint()}
    assert auth._session_valid(session)
    monkeypatch.setattr(config, "WEBUI_PASSWORD", "new")
    assert not auth._session_valid(session)
    assert not auth._session_valid({"authenticated": True})   # sessions from before this check


def test_panel_is_never_indexed():
    from webui import auth, theme
    assert "/robots.txt" in auth.UNRESTRICTED
    assert 'name="robots" content="noindex' in theme._HEAD
