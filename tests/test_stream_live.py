from unittest.mock import patch

import scripts.stream_live as stream_live


def test_dead_nowplaying_file_constants_are_gone():
    # Regression guard for the Phase 5 cleanup: these wrote to hardcoded
    # POSIX-only /tmp paths that nothing in the codebase ever read.
    assert not hasattr(stream_live, "NOWPLAYING_FILE")
    assert not hasattr(stream_live, "GENRE_FILE")
    assert not hasattr(stream_live, "_write_nowplaying")


def test_send_alert_noop_when_webhook_unset():
    with patch.object(stream_live, "_ALERT_WEBHOOK", ""):
        with patch("requests.post") as mock_post:
            stream_live._send_alert("test message")
    mock_post.assert_not_called()


def test_send_alert_posts_when_webhook_set():
    with patch.object(stream_live, "_ALERT_WEBHOOK", "https://example.invalid/webhook"):
        with patch("requests.post") as mock_post:
            stream_live._send_alert("test message")
    mock_post.assert_called_once()
    _args, kwargs = mock_post.call_args
    assert "test message" in kwargs["json"]["text"]


def test_send_alert_never_raises_on_network_failure():
    with patch.object(stream_live, "_ALERT_WEBHOOK", "https://example.invalid/webhook"):
        with patch("requests.post", side_effect=Exception("network down")):
            stream_live._send_alert("test message")  # must not raise


def test_alert_threshold_constants_are_sane():
    assert stream_live._ALERT_AFTER_ATTEMPTS > 0
    assert stream_live._ALERT_REPEAT_EVERY > 0
