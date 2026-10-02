"""Every YouTube API call path, run against Google's own API definition
(see tests/youtube_contract.py). A failure names the method and the field."""
import types

import pytest

from youtube_contract import install   # tests/ is on sys.path (rootdir conftest)


@pytest.fixture
def rec(monkeypatch, tmp_path):
    r = install(monkeypatch)
    monkeypatch.setenv("YT_GENRE_PLAYLISTS", "1")
    return r


def _video(tmp_path):
    p = tmp_path / "v.mp4"
    p.write_bytes(b"\0" * 2048)
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"\xff\xd8\xff" + b"\0" * 64)
    return str(p), str(thumb)


def _seo():
    return {"title": "rain on the window 🌧️ [lofi jazz · 1 hour]", "description": "d",
            "tags": ["lofi jazz", "study music"], "category_id": "10", "privacy": "public",
            "made_for_kids": False, "genre_label": "lofi jazz", "pillar": "temporal"}


def test_upload_thumbnail_and_playlists(rec, tmp_path):
    from scripts import upload_youtube as up
    video, thumb = _video(tmp_path)
    vid, url = up.upload_video(rec.client(), video, _seo(), thumb)
    assert vid and url
    assert "youtube.videos.insert" in rec.methods()
    assert "youtube.thumbnails.set" in rec.methods()
    assert rec.violations == []


def test_scheduled_upload(rec, tmp_path):
    from scripts import upload_youtube as up
    video, _ = _video(tmp_path)
    up.upload_video(rec.client(), video, _seo(), None, publish_at="2026-10-03T08:00:00.000Z")
    body = next(b for m, _, b in rec.calls if m == "youtube.videos.insert")
    assert body["status"]["privacyStatus"] == "private" and body["status"]["publishAt"]
    assert rec.violations == []


def test_panel_edit_comments_thumbnail(rec, tmp_path):
    from webui import stats
    yt = rec.client()
    _, thumb = _video(tmp_path)
    assert stats.get_video_details("v1", client=yt)
    assert stats.update_video("v1", title="t", description="d", tags=["a"],
                              privacy="private", client=yt)
    assert stats.set_video_thumbnail("v1", thumb, client=yt)
    assert stats.list_comments("v1", force=True, client=yt) is not None
    assert stats.set_comment_moderation("c1", "published", client=yt)
    assert stats.reply_to_comment("c1", "thanks!", client=yt) is not None
    assert stats.delete_comment("c1", client=yt)
    assert rec.violations == []


def test_panel_analytics_reports(rec):
    from webui import stats
    yta = rec.client("youtubeAnalytics", "v2")
    assert stats.traffic_sources(force=True, client=yta) is not None
    assert stats.subscriber_growth(force=True, client=yta) is not None
    assert rec.violations == []


def test_live_broadcast_lifecycle(rec, monkeypatch):
    import publish
    yt = rec.client()
    bid, _ = publish._create_broadcast(yt, "lofi hip hop radio 🌧️ beats", "d",
                                       "2026-10-02T10:00:00.000Z", "public")
    sid, key = publish._create_stream(yt, "lofi_stream_x")
    publish._bind_broadcast(yt, bid, sid)
    publish._transition_broadcast(yt, bid, "testing")
    assert key
    monkeypatch.setattr(publish, "get_youtube", lambda: yt)
    monkeypatch.setattr(publish, "load_live_state", lambda: None)
    publish.cmd_rename(types.SimpleNamespace(broadcast_id=bid, title="new title"))
    update = next(b for m, _, b in rec.calls if m == "youtube.liveBroadcasts.update")
    assert update["snippet"]["description"] == "keep me"
    assert rec.violations == []


def test_24_7_stream_setup_and_title_updates(rec, monkeypatch):
    from scripts import youtube_live_manager as ylm
    yt = rec.client()
    monkeypatch.setattr(ylm, "get_youtube_service", lambda: yt)
    monkeypatch.setattr(ylm, "_find_broadcast", lambda *a: None)   # force a fresh one
    info = ylm.setup_live_stream(theme_name="cozy_rain")
    assert info["broadcast_id"] and info["rtmp_url"].startswith("rtmp://")
    assert info["title"].startswith("lofi hip hop radio")
    ylm.end_broadcast(yt, info["broadcast_id"])
    assert rec.violations == []


def test_trend_research_queries(rec, monkeypatch):
    from scripts import trend_research as tr
    monkeypatch.setattr(tr, "YOUTUBE_API_KEY", "k")
    tr.fetch_yt_trending(max_results=8)
    assert "youtube.search.list" in rec.methods()
    assert rec.violations == []


def test_genre_playlist_creation(rec):
    from scripts import playlist_curation as pc
    yt = rec.client()
    pc.genre_playlist_id(yt, "lofi jazz", env={"YT_GENRE_PLAYLISTS": "1"})
    assert rec.violations == []


# ── the checker itself catches the bugs it exists for ──────────────────────
def test_checker_flags_read_only_unknown_wrong_type_and_unrequested_parts(rec):
    yt = rec.client()
    yt.videos().update(part="snippet", body={
        "id": "v1",
        "snippet": {"title": "t", "categoryId": "10", "tittle": "typo"},
        "status": {"madeForKids": False, "embeddable": "yes"},
    }).execute()
    text = "\n".join(rec.violations)
    assert "read-only field Video.status.madeForKids" in text
    assert "unknown field Video.snippet.tittle" in text
    assert "Video.status.embeddable should be boolean" in text
    assert "body has ['status'] but part='snippet'" in text


def test_checker_flags_bad_parameter_names(rec):
    with pytest.raises(TypeError):
        rec.client().videos().list(part="snippet", videoId="v1")   # the parameter is `id`


# ── paths that load OAuth credentials themselves ───────────────────────────
@pytest.fixture
def creds(monkeypatch, tmp_path):
    token = tmp_path / "token.json"
    token.write_text("{}")
    fake = types.SimpleNamespace(expired=False, refresh_token=None, valid=True)
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_file",
                        lambda *a, **k: fake)
    from webui import config
    from scripts import analytics
    monkeypatch.setattr(config, "TOKEN_FILE", str(token))
    monkeypatch.setattr(analytics, "TOKEN_FILE", str(token))
    return token


def test_panel_channel_numbers(rec, creds):
    from webui import stats
    assert stats.channel_stats(force=True)["ok"]
    assert stats.video_engagement(["v1"], force=True) is not None
    stats.retention("v1")
    assert rec.violations == []


def test_analytics_sync_and_thumbnail_swap(rec, creds, monkeypatch, tmp_path):
    import datetime
    import json
    from scripts import analytics
    when = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)).isoformat()
    log = tmp_path / "upload_log.json"
    log.write_text(json.dumps([{"type": "upload", "video_id": "abcdefghijk", "title": "t",
                                "timestamp": when, "thumb_file": "thumb_cozy_rain_20260901_000000.jpg"}]))
    monkeypatch.setattr(analytics, "UPLOAD_LOG", str(log))
    monkeypatch.setattr(analytics, "ANALYTICS_LOG", str(tmp_path / "analytics_log.json"))
    monkeypatch.setenv("YT_CHANNEL_ID", "UC1")
    analytics.sync_analytics()
    assert any(m.startswith("youtubeAnalytics.reports.query") for m in rec.methods())
    assert rec.violations == []


def test_cli_upload_guard_delete_and_playlists(rec, monkeypatch, tmp_path):
    import publish
    yt = rec.client()
    monkeypatch.setattr(publish, "get_youtube", lambda: yt)
    publish.cmd_delete(types.SimpleNamespace(video_id="v1", yes=True))
    publish.cmd_playlist(types.SimpleNamespace(playlist_cmd="list"))
    publish.cmd_playlist(types.SimpleNamespace(playlist_cmd="add", video_id="v1", playlist_id="PL1"))
    publish._wait_for_stream_active(yt, "s1", timeout=1)
    assert {"youtube.videos.delete", "youtube.playlists.list",
            "youtube.playlistItems.insert", "youtube.liveStreams.list"} <= set(rec.methods())
    assert rec.violations == []


def test_live_title_updater_and_midnight_refresh(rec, monkeypatch):
    import time
    import publish
    from scripts import youtube_live_manager as ylm
    yt = rec.client()
    monkeypatch.setattr(ylm, "_TITLE_COOLDOWN", 0)
    real_sleep = time.sleep
    monkeypatch.setattr(ylm.time, "sleep", lambda s: real_sleep(0.01))
    up = ylm.LiveTitleUpdater(yt, "b1", "2026-10-02T10:00:00Z")
    up.set_track("Until the Small Hours", "lofi_jazz")
    for _ in range(300):
        if "youtube.liveBroadcasts.update" in rec.methods():
            break
        real_sleep(0.01)
    up.stop()
    up._thread.join(timeout=2)
    monkeypatch.setattr(ylm, "get_youtube_service", lambda: yt)
    monkeypatch.setattr(publish, "load_live_state", lambda: {"theme": "cozy_rain",
                                                             "genre_label": "lofi jazz"})
    monkeypatch.setattr("scripts.trend_research.get_trend_snapshot", lambda: None)
    publish._do_midnight_refresh("b1")
    assert rec.methods().count("youtube.liveBroadcasts.update") >= 2
    assert rec.violations == []
