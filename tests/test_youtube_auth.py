"""Auth must never hang an unattended run or throw away a good token."""
import json
import sys

import pytest
from google.oauth2.credentials import Credentials

from scripts import upload_youtube as uy


@pytest.fixture
def token(tmp_path, monkeypatch):
    path = tmp_path / "token.json"
    path.write_text(json.dumps({
        "token": "x", "refresh_token": "r", "client_id": "c", "client_secret": "s",
        "token_uri": "https://oauth2.googleapis.com/token", "expiry": "2000-01-01T00:00:00Z",
    }))
    monkeypatch.setattr(uy, "TOKEN_FILE", str(path))
    monkeypatch.setattr(uy, "CLIENT_SECRET", str(tmp_path / "client_secret.json"))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    return path


def test_network_error_during_refresh_keeps_the_token(token, monkeypatch):
    def boom(self, request):
        raise ConnectionError("network down")
    monkeypatch.setattr(Credentials, "refresh", boom)
    with pytest.raises(ConnectionError):
        uy.get_authenticated_service()
    assert token.exists()


def test_unattended_run_without_login_exits_instead_of_waiting(token, monkeypatch):
    from google.auth.exceptions import RefreshError

    def rejected(self, request):
        raise RefreshError("invalid_grant")
    monkeypatch.setattr(Credentials, "refresh", rejected)
    with pytest.raises(SystemExit):
        uy.get_authenticated_service()
    assert not token.exists()


def test_end_only_signals_real_ffmpeg_processes():
    import os
    import publish
    assert not publish._is_ffmpeg(os.getpid())
    assert not publish._is_ffmpeg(2 ** 22 + 7)
