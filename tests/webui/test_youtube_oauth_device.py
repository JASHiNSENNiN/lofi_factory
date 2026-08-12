"""
Unit tests for the device-code OAuth flow (youtube_oauth.py) -- mocks the
Google HTTP endpoints so these run offline/fast, unlike the live-endpoint
verification done manually during development (real 401 against a fake
client_id, confirmed the request shape is accepted by Google's server).
"""
from __future__ import annotations

import json
import os

import pytest

from webui import config, youtube_oauth


@pytest.fixture(autouse=True)
def _isolated_device_client(tmp_path, monkeypatch):
    device_client = tmp_path / "client_secret_device.json"
    device_client.write_text(json.dumps({
        "installed": {"client_id": "test-client-id", "client_secret": "test-secret"}
    }))
    monkeypatch.setattr(config, "CLIENT_SECRET_DEVICE", str(device_client))
    monkeypatch.setattr(config, "TOKEN_FILE", str(tmp_path / "token.json"))
    return device_client


class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_device_client_status_reports_presence():
    assert youtube_oauth.device_client_status() == {"present": True, "client_type": "installed"}


def test_device_client_status_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CLIENT_SECRET_DEVICE", str(tmp_path / "nope.json"))
    st = youtube_oauth.device_client_status()
    assert st["present"] is False


def test_device_flow_start_missing_client_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CLIENT_SECRET_DEVICE", str(tmp_path / "nope.json"))
    with pytest.raises(FileNotFoundError):
        youtube_oauth.device_flow_start()


def test_device_flow_start_returns_expected_fields(monkeypatch):
    def fake_post(url, data=None, timeout=None):
        assert url == youtube_oauth._DEVICE_CODE_URL
        assert data["client_id"] == "test-client-id"
        return _FakeResponse(200, {
            "device_code": "dc-123", "user_code": "ABCD-EFGH",
            "verification_url": "https://google.com/device",
            "interval": 5, "expires_in": 1800,
        })

    monkeypatch.setattr("requests.post", fake_post)
    result = youtube_oauth.device_flow_start()
    assert result["device_code"] == "dc-123"
    assert result["user_code"] == "ABCD-EFGH"
    assert result["verification_url"] == "https://google.com/device"
    assert result["interval"] == 5


def test_device_flow_poll_pending_raises_pending(monkeypatch):
    monkeypatch.setattr("requests.post",
                         lambda *a, **k: _FakeResponse(400, {"error": "authorization_pending"}))
    with pytest.raises(youtube_oauth.DeviceFlowPending):
        youtube_oauth.device_flow_poll("dc-123")


def test_device_flow_poll_denied_raises_runtime_error(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: _FakeResponse(
        400, {"error": "access_denied", "error_description": "user declined"}))
    with pytest.raises(RuntimeError, match="access_denied"):
        youtube_oauth.device_flow_poll("dc-123")


def test_device_flow_poll_success_writes_token(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: _FakeResponse(200, {
        "access_token": "at-123", "refresh_token": "rt-456",
    }))
    youtube_oauth.device_flow_poll("dc-123")
    assert os.path.exists(config.TOKEN_FILE)
    saved = json.loads(open(config.TOKEN_FILE).read())
    assert saved["refresh_token"] == "rt-456"
