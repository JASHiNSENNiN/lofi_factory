"""
Unit tests for the opt-in monetary-analytics consent flow in
webui/youtube_oauth.py (monetary_status / monetary_authorization_url /
monetary_handle_callback / monetary_disconnect). Mocks
google_auth_oauthlib.flow.Flow so these run offline, same convention as
tests/webui/test_youtube_oauth_device.py uses for the device-code flow.

The key guarantee under test: this flow is entirely separate from the main
login -- it writes to config.TOKEN_FILE_MONETARY, never config.TOKEN_FILE,
and requests config.MONETARY_SCOPES, never config.SCOPES.
"""
from __future__ import annotations

import json

import pytest

from webui import config, youtube_oauth


class _FakeCredentials:
    def __init__(self, scopes):
        self.token = "fake-access-token"
        self.refresh_token = "fake-refresh-token"
        self._scopes = scopes

    def to_json(self):
        return json.dumps({
            "token": self.token,
            "refresh_token": self.refresh_token,
            "scopes": self._scopes,
        })


class _FakeFlow:
    last_instance = None

    def __init__(self, scopes):
        self.scopes = scopes
        self.redirect_uri = None
        self.fetched_code = None
        self.credentials = _FakeCredentials(scopes)
        _FakeFlow.last_instance = self

    @classmethod
    def from_client_secrets_file(cls, path, scopes=None):
        return cls(scopes)

    def authorization_url(self, **kwargs):
        return "https://accounts.google.com/fake-consent", "fake-state-xyz"

    def fetch_token(self, code=None):
        self.fetched_code = code


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    client_secret = tmp_path / "client_secret.json"
    client_secret.write_text(json.dumps({"web": {"client_id": "x", "client_secret": "y"}}))
    monkeypatch.setattr(config, "CLIENT_SECRET", str(client_secret))
    monkeypatch.setattr(config, "TOKEN_FILE", str(tmp_path / "token.json"))
    monkeypatch.setattr(config, "TOKEN_FILE_MONETARY", str(tmp_path / "token_monetary.json"))
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")

    import google_auth_oauthlib.flow as flow_mod
    monkeypatch.setattr(flow_mod, "Flow", _FakeFlow)

    monkeypatch.setattr(youtube_oauth, "_pending_state_monetary", None)
    yield
    monkeypatch.setattr(youtube_oauth, "_pending_state_monetary", None)


def test_monetary_status_not_connected_by_default():
    st = youtube_oauth.monetary_status()
    assert st["connected"] is False
    assert st["client_present"] is True
    assert st["redirect_uri"].endswith("/youtube/monetary/callback")


def test_monetary_authorization_url_requests_monetary_scopes():
    url = youtube_oauth.monetary_authorization_url()
    assert url == "https://accounts.google.com/fake-consent"
    assert _FakeFlow.last_instance.scopes == config.MONETARY_SCOPES
    assert youtube_oauth._pending_state_monetary == "fake-state-xyz"


def test_monetary_authorization_url_does_not_request_base_scopes_only():
    youtube_oauth.monetary_authorization_url()
    # Must be the superset (base + monetary), never just config.SCOPES.
    assert _FakeFlow.last_instance.scopes != config.SCOPES


def test_monetary_handle_callback_writes_separate_token_file():
    youtube_oauth.monetary_authorization_url()
    youtube_oauth.monetary_handle_callback("auth-code-123", "fake-state-xyz")

    import os
    assert os.path.exists(config.TOKEN_FILE_MONETARY)
    assert not os.path.exists(config.TOKEN_FILE)  # main token untouched

    tok = json.loads(open(config.TOKEN_FILE_MONETARY).read())
    assert tok["scopes"] == config.MONETARY_SCOPES


def test_monetary_handle_callback_rejects_state_mismatch():
    youtube_oauth.monetary_authorization_url()
    with pytest.raises(ValueError):
        youtube_oauth.monetary_handle_callback("auth-code-123", "wrong-state")


def test_monetary_disconnect_removes_token_file(tmp_path, monkeypatch):
    token = tmp_path / "token_monetary.json"
    token.write_text("{}")
    monkeypatch.setattr(config, "TOKEN_FILE_MONETARY", str(token))

    youtube_oauth.monetary_disconnect()

    assert not token.exists()


def test_monetary_disconnect_missing_file_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN_FILE_MONETARY", str(tmp_path / "nope.json"))
    youtube_oauth.monetary_disconnect()  # must not raise
