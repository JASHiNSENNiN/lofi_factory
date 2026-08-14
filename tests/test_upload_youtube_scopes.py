"""
Guardrail tests for the opt-in monetary-analytics scope (see webui/app.py's
"Revenue & RPM" Settings card and webui/youtube_oauth.py's monetary_* flow).

Revenue/RPM data needs yt-analytics-monetary.readonly, which must NEVER be
folded into the default SCOPES list used by the normal YouTube login/upload
flow -- doing so would force every existing user to hit a surprise new
consent screen (and re-authenticate lofi-auto's unattended token) just from
an unrelated login. These tests fail loudly if that ever happens, whether by
accident in scripts/upload_youtube.py or its webui/config.py mirror.
"""
from scripts import upload_youtube
from webui import config

_MONETARY_SCOPE = "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"

_BASELINE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def test_upload_youtube_default_scopes_do_not_include_monetary_scope():
    assert _MONETARY_SCOPE not in upload_youtube.SCOPES


def test_upload_youtube_default_scopes_match_known_baseline():
    # Locks the exact scope list -- any addition (monetary or otherwise) to
    # SCOPES must be a deliberate, reviewed change, not a silent merge.
    assert upload_youtube.SCOPES == _BASELINE_SCOPES


def test_upload_youtube_monetary_scopes_is_a_separate_constant():
    assert hasattr(upload_youtube, "MONETARY_SCOPES")
    assert upload_youtube.MONETARY_SCOPES != upload_youtube.SCOPES
    assert _MONETARY_SCOPE in upload_youtube.MONETARY_SCOPES
    # Superset of the base scopes plus the one extra monetary scope.
    assert set(upload_youtube.SCOPES).issubset(set(upload_youtube.MONETARY_SCOPES))
    assert len(upload_youtube.MONETARY_SCOPES) == len(upload_youtube.SCOPES) + 1


def test_webui_config_default_scopes_do_not_include_monetary_scope():
    assert _MONETARY_SCOPE not in config.SCOPES


def test_webui_config_default_scopes_match_known_baseline():
    assert config.SCOPES == _BASELINE_SCOPES


def test_webui_config_monetary_scopes_is_a_separate_constant():
    assert hasattr(config, "MONETARY_SCOPES")
    assert config.MONETARY_SCOPES != config.SCOPES
    assert _MONETARY_SCOPE in config.MONETARY_SCOPES
    assert set(config.SCOPES).issubset(set(config.MONETARY_SCOPES))


def test_webui_config_has_separate_monetary_token_file_path():
    # Revenue/RPM must never be stored in (or gate on) the regular token.json.
    assert config.TOKEN_FILE_MONETARY != config.TOKEN_FILE
