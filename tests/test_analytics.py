import datetime
import json

import scripts.analytics as analytics_mod
from scripts.analytics import title_variant_weights

DURATION_MAP = {"1 hour": 3600, "2 hours": 7200, "3 hours": 10800}


def test_title_variant_weights_empty():
    assert title_variant_weights({}) == {}


def test_title_variant_weights_prefers_higher_ctr_variant():
    # Keyed by hook-strategy identity (not raw slot index) -- see
    # generate_seo.py's HOOK_STRATEGIES. "scene" (idx 0) outperforms
    # "moment" (idx 1) here, so its weight should end up higher.
    fake = {}
    for i in range(6):
        fake[f"t0_{i}"] = {"pillar": "temporal", "title_chosen_strategy": "scene",
                            "videoThumbnailImpressionsClickRate": 0.06}
    for i in range(6):
        fake[f"t1_{i}"] = {"pillar": "temporal", "title_chosen_strategy": "moment",
                            "videoThumbnailImpressionsClickRate": 0.02}
    result = title_variant_weights(fake)
    assert result["temporal"]["scene"] > result["temporal"]["moment"]


def test_title_variant_weights_keys_by_explicit_strategy_when_present():
    # When entries already carry title_chosen_strategy (the new field), that
    # takes priority over the title_chosen_idx fallback mapping.
    fake = {}
    for i in range(6):
        fake[f"s0_{i}"] = {"pillar": "temporal", "title_chosen_strategy": "radio",
                            "videoThumbnailImpressionsClickRate": 0.08}
    for i in range(6):
        fake[f"s1_{i}"] = {"pillar": "temporal", "title_chosen_strategy": "scene",
                            "videoThumbnailImpressionsClickRate": 0.01}
    result = title_variant_weights(fake)
    assert result["temporal"]["radio"] > result["temporal"]["scene"]


def test_title_variant_weights_skips_pillars_below_threshold():
    fake = {f"v{i}": {"pillar": "aesthetic", "title_chosen_strategy": "scene",
                       "videoThumbnailImpressionsClickRate": 0.05} for i in range(3)}
    assert title_variant_weights(fake) == {}


def test_title_variant_weights_is_deterministic_and_keyed_by_hook_strategy():
    # The bandit dimension was extended from raw title_variants[] slot index
    # to hook-strategy identity (see generate_seo.py's HOOK_STRATEGIES). The
    # underlying weight is an analytic Beta posterior mean (no sampling), so
    # repeated calls on the same data must be bit-for-bit identical, and the
    # returned per-pillar dict must be keyed by strategy name, not int index.
    # Non-constant per-arm CTRs (rather than one repeated value) so the
    # pooled median used for success/failure binarization doesn't land
    # exactly on an arm's value and produce a spurious tie between arms.
    spec_led_ctrs     = [0.09, 0.085, 0.08, 0.075, 0.07, 0.065, 0.06, 0.095]
    statement_ctrs    = [0.05, 0.048, 0.052, 0.045, 0.05, 0.049, 0.051, 0.047]
    benefit_list_ctrs = [0.02, 0.015, 0.025, 0.01, 0.02, 0.018, 0.022, 0.017]

    fake = {}
    for i, v in enumerate(spec_led_ctrs):
        fake[f"a{i}"] = {"pillar": "activity", "title_chosen_strategy": "radio",
                          "videoThumbnailImpressionsClickRate": v}
    for i, v in enumerate(benefit_list_ctrs):
        fake[f"b{i}"] = {"pillar": "activity", "title_chosen_strategy": "moment",
                          "videoThumbnailImpressionsClickRate": v}
    for i, v in enumerate(statement_ctrs):
        fake[f"c{i}"] = {"pillar": "activity", "title_chosen_strategy": "scene",
                          "videoThumbnailImpressionsClickRate": v}

    result_1 = title_variant_weights(fake)
    result_2 = title_variant_weights(fake)
    assert result_1 == result_2  # deterministic

    weights = result_1["activity"]
    assert set(weights.keys()) <= {"scene", "moment", "radio"}
    assert all(isinstance(k, str) for k in weights)  # keyed by strategy name, not int
    assert weights["radio"] > weights["scene"] > weights["moment"]


# ── title_features() / title_feature_weights() ──────────────────────────────
# Finer-grained than title_variant_weights(): mines the already-logged title
# *text* (length/emoji/benefit-list-shape) instead of only hook-strategy
# identity, so the bandit can eventually learn "does a target-length title
# outperform a long one" independent of which hook family it came from.
def test_title_features_buckets_length_and_benefit_list():
    short_title = "lofi beats"
    features = analytics_mod.title_features(short_title)
    assert features["length_bucket"] == "short_lt45"
    assert features["benefit_list"] == "no_benefit_list"
    assert features["has_emoji"] == "no_emoji"

    target_title = "lofi hip hop mix for study focus and relax sessions"
    assert 45 <= len(target_title) <= 70
    features2 = analytics_mod.title_features(target_title)
    assert features2["length_bucket"] == "target_45_70"
    assert features2["benefit_list"] == "benefit_list"  # 3 vocab hits: study, focus, relax

    long_title = "x" * 80
    assert analytics_mod.title_features(long_title)["length_bucket"] == "long_gt70"


def test_title_features_detects_emoji():
    assert analytics_mod.title_features("lofi beats \U0001F319 for sleep")["has_emoji"] == "emoji"
    assert analytics_mod.title_features("lofi beats for sleep")["has_emoji"] == "no_emoji"


def test_title_feature_weights_empty():
    assert analytics_mod.title_feature_weights({}) == {}


def test_title_feature_weights_rewards_target_length_bucket():
    fake = {}
    for i in range(6):
        fake[f"short_{i}"] = {"title": "lofi beats",  # short_lt45
                               "videoThumbnailImpressionsClickRate": 0.01}
    for i in range(6):
        fake[f"target_{i}"] = {"title": "lofi hip hop mix for a long study focus session tonight",  # target_45_70
                                "videoThumbnailImpressionsClickRate": 0.08}
    result = analytics_mod.title_feature_weights(fake)
    assert result["length_bucket"]["target_45_70"] > result["length_bucket"]["short_lt45"]


def test_title_feature_weights_rewards_benefit_list_titles():
    fake = {}
    for i in range(6):
        fake[f"nobenefit_{i}"] = {"title": "lofi hip hop late night session tonight only",
                                   "videoThumbnailImpressionsClickRate": 0.01}
    for i in range(6):
        fake[f"benefit_{i}"] = {"title": "lofi hip hop mix - study, focus, relax and sleep tonight",
                                 "videoThumbnailImpressionsClickRate": 0.09}
    result = analytics_mod.title_feature_weights(fake)
    assert result["benefit_list"]["benefit_list"] > result["benefit_list"]["no_benefit_list"]


def test_title_feature_weights_skips_entries_without_title():
    fake = {f"v{i}": {"videoThumbnailImpressionsClickRate": 0.05} for i in range(6)}
    assert analytics_mod.title_feature_weights(fake) == {}


# ── thumbnail A/B swap: alt-file lookup ────────────────────────────────────
# The feature previously derived the expected alt filename from the video's
# own timestamp (thumb_{video_ts}_alt.jpg) -- but that never matched real
# thumbnail filenames (which carry a theme prefix and their own, separately
# generated timestamp). Nothing ever populated an alt file either. Fixed by
# logging the exact thumbnail filename at upload time (thumb_file) and
# deriving the alt path directly from it.
def test_swap_thumbnails_finds_alt_file_via_logged_thumb_file(tmp_path, monkeypatch, capsys):
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    primary = assets_dir / "thumb_cozy_rain_20260805_120000.jpg"
    alt = assets_dir / "thumb_cozy_rain_20260805_120000_alt.jpg"
    primary.write_bytes(b"fake-primary")
    alt.write_bytes(b"fake-alt")

    upload_log = tmp_path / "upload_log.json"
    old_ts = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=10)).isoformat()
    upload_log.write_text(json.dumps([{
        "type": "upload", "video_id": "dQw4w9WgXcQ",
        "video_file": "lofi_20260805_120530.mp4",
        "thumb_file": "thumb_cozy_rain_20260805_120000.jpg",
        "timestamp": old_ts,
    }]))

    monkeypatch.setattr(analytics_mod, "ROOT", str(tmp_path))
    monkeypatch.setattr(analytics_mod, "UPLOAD_LOG", str(upload_log))
    monkeypatch.setattr(analytics_mod, "TOKEN_FILE", str(tmp_path / "no_such_token.json"))

    old_date = (datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    # Large, well-separated impression counts so the two-proportion z-test
    # (which replaced the old flat CTR<70%-of-average heuristic) reaches
    # significance (p < 0.05) -- this is deliberately an extreme CTR gap at
    # high volume, not a borderline case.
    fake_analytics = {
        "dQw4w9WgXcQ": {"videoThumbnailImpressionsClickRate": 0.01,
                         "videoThumbnailImpressions": 5000, "upload_date": old_date},
        "other_vid":   {"videoThumbnailImpressionsClickRate": 0.05,
                         "videoThumbnailImpressions": 5000, "upload_date": old_date},
    }

    analytics_mod.swap_low_ctr_thumbnails(fake_analytics)

    # It should have found the alt file and attempted the swap (failing only
    # on the missing token, which is expected here) -- not silently skipped
    # the video because the alt-path guess didn't match anything.
    out = capsys.readouterr().out
    assert "dQw4w9WgXcQ" in out
    assert "failed" in out  # no real token.json in this test -- expected


def test_swap_thumbnails_skips_video_with_no_alt_file(tmp_path, monkeypatch, capsys):
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    # Primary exists, but no _alt.jpg was ever generated for it.
    (assets_dir / "thumb_cozy_rain_20260805_120000.jpg").write_bytes(b"fake-primary")

    upload_log = tmp_path / "upload_log.json"
    old_ts = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=10)).isoformat()
    upload_log.write_text(json.dumps([{
        "type": "upload", "video_id": "noAltVideoId",
        "video_file": "lofi_20260805_120530.mp4",
        "thumb_file": "thumb_cozy_rain_20260805_120000.jpg",
        "timestamp": old_ts,
    }]))

    monkeypatch.setattr(analytics_mod, "ROOT", str(tmp_path))
    monkeypatch.setattr(analytics_mod, "UPLOAD_LOG", str(upload_log))

    old_date = (datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    fake_analytics = {
        "noAltVideoId": {"videoThumbnailImpressionsClickRate": 0.01,
                          "videoThumbnailImpressions": 5000, "upload_date": old_date},
        "other_vid":    {"videoThumbnailImpressionsClickRate": 0.05,
                          "videoThumbnailImpressions": 5000, "upload_date": old_date},
    }

    analytics_mod.swap_low_ctr_thumbnails(fake_analytics)

    out = capsys.readouterr().out
    assert "noAltVideoId" not in out  # skipped cleanly, no attempted API call


def test_title_variant_weights_ignores_retired_title_forms():
    fake = {f"o{i}": {"pillar": "temporal", "title_chosen_strategy": "benefit_list",
                      "ctr": 0.05, "impressions": 1000} for i in range(10)}
    fake.update({f"x{i}": {"pillar": "temporal", "title_chosen_idx": 0,
                           "ctr": 0.05, "impressions": 1000} for i in range(10)})
    assert title_variant_weights(fake) == {}


def test_title_features_tell_current_titles_apart():
    f = analytics_mod.title_features
    scene = f("first snow of winter ❄️ [lofi jazz · 1 hour]")
    moment = f("coding after midnight 🌙 [jazz hop · 1 hour]")
    assert scene["seasonal"] == "seasonal" and moment["seasonal"] == "evergreen"
    assert moment["time_of_day"] == "time" and scene["time_of_day"] == "no_time"
    assert scene["length_band"] == "40_62"
