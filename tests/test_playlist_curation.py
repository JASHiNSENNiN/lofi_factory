"""Unit tests for scripts/playlist_curation.py's pillar-based playlist assignment."""
from __future__ import annotations

from scripts import playlist_curation as pc


def test_resolves_by_pillar_env_var():
    env = {"YT_PLAYLIST_ACTIVITY": "PLactivity123"}
    seo = {"pillar": "activity", "duration": "2 hours"}
    assert pc.resolve_playlist_id(seo, env=env) == "PLactivity123"


def test_pillar_lookup_is_case_insensitive():
    env = {"YT_PLAYLIST_EMOTIONAL": "PLemo1"}
    seo = {"pillar": "Emotional"}
    assert pc.resolve_playlist_id(seo, env=env) == "PLemo1"


def test_falls_back_to_legacy_duration_mapping_when_pillar_var_unset():
    env = {"YT_PLAYLIST_SLEEP": "PLsleep1", "YT_PLAYLIST_STUDY": "PLstudy1"}
    seo = {"pillar": "temporal", "duration": "all night"}
    assert pc.resolve_playlist_id(seo, env=env) == "PLsleep1"

    seo_short = {"pillar": "temporal", "duration": "1 hour"}
    assert pc.resolve_playlist_id(seo_short, env=env) == "PLstudy1"


def test_pillar_var_takes_priority_over_legacy_fallback():
    env = {"YT_PLAYLIST_ACTIVITY": "PLactivity", "YT_PLAYLIST_STUDY": "PLstudy1"}
    seo = {"pillar": "activity", "duration": "1 hour"}
    assert pc.resolve_playlist_id(seo, env=env) == "PLactivity"


def test_unknown_pillar_falls_back_to_legacy():
    env = {"YT_PLAYLIST_STUDY": "PLstudy1"}
    seo = {"pillar": "geographic", "duration": "1 hour"}  # not a real pillar
    assert pc.resolve_playlist_id(seo, env=env) == "PLstudy1"


def test_no_matching_env_var_returns_none():
    seo = {"pillar": "aesthetic", "duration": "2 hours"}
    assert pc.resolve_playlist_id(seo, env={}) is None


def test_missing_pillar_field_still_falls_back_to_legacy():
    env = {"YT_PLAYLIST_STUDY": "PLstudy1"}
    seo = {"duration": "1 hour"}
    assert pc.resolve_playlist_id(seo, env=env) == "PLstudy1"


def test_blank_env_value_treated_as_unset():
    env = {"YT_PLAYLIST_ACTIVITY": "   ", "YT_PLAYLIST_STUDY": "PLstudy1"}
    seo = {"pillar": "activity", "duration": "1 hour"}
    assert pc.resolve_playlist_id(seo, env=env) == "PLstudy1"


def test_all_five_pillars_have_env_var_mappings():
    assert set(pc.PILLAR_ENV_VARS) == set(pc.PILLARS)
    assert len(pc.PILLARS) == 5


class _FakeInsert:
    def __init__(self, resp):
        self._resp = resp

    def execute(self):
        return self._resp


class _FakePlaylists:
    def __init__(self):
        self.insert_calls = []

    def insert(self, part, body):
        self.insert_calls.append({"part": part, "body": body})
        return _FakeInsert({"id": "PLnew123", "snippet": {"title": body["snippet"]["title"]}})


class _FakeYouTube:
    def __init__(self):
        self.playlists_obj = _FakePlaylists()

    def playlists(self):
        return self.playlists_obj


def test_create_playlist_noop_without_confirm():
    yt = _FakeYouTube()
    result = pc.create_playlist_if_confirmed(yt, "Focus Sessions", confirm=False)
    assert result is None
    assert yt.playlists_obj.insert_calls == []


def test_create_playlist_calls_api_when_confirmed():
    yt = _FakeYouTube()
    result = pc.create_playlist_if_confirmed(yt, "Focus Sessions", confirm=True)
    assert result == {"id": "PLnew123", "title": "Focus Sessions"}
    assert len(yt.playlists_obj.insert_calls) == 1
    assert yt.playlists_obj.insert_calls[0]["body"]["snippet"]["title"] == "Focus Sessions"
