"""
analytics.py — YouTube Analytics per-video tracking and pillar performance reporting.

Fetches CTR, impressions, views, and watch time for each uploaded video after it has
had at least MIN_AGE_DAYS of data. Stores results locally in assets/analytics_log.json
as an append-only longitudinal time series (one dated snapshot per sync per video,
not a single overwritten row) -- this is the foundation the pillar/duration/title
bandit weighting, forecasting, and change-point detection below all build on.

Usage:
    python scripts/analytics.py                # sync eligible videos
    python scripts/analytics.py --report       # sync + print CTR by pillar
    python scripts/analytics.py --swap-thumbs  # sync + swap low-CTR thumbnails (z-test gated)
"""
import argparse
import datetime
import json
import math
import os
import random
import re
import statistics
import sys

from scripts.bandit import ThompsonSamplingBandit

ROOT          = os.path.join(os.path.dirname(__file__), "..")

from scripts.upload_youtube import SCOPES as _ANALYTICS_SCOPES  # noqa: E402
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
UPLOAD_LOG    = os.path.join(ROOT, "upload_log.json")
ANALYTICS_LOG = os.path.join(ROOT, "assets", "analytics_log.json")
TOKEN_FILE    = os.path.join(ROOT, "token.json")
MIN_AGE_DAYS  = 7
MAX_AGE_DAYS  = 90   # stop tracking after 90 days (stable)

# Metrics split by query type — engagement supports per-video filter;
# reach metrics are channel-scoped and require dimensions=video.
# See fetch_video_metrics() for how these are used.
METRICS_ENGAGEMENT = "views,estimatedMinutesWatched,averageViewDuration,likes,comments"
METRICS_REACH      = "videoThumbnailImpressions,videoThumbnailImpressionsClickRate"

# Metric fields that live inside a per-sync snapshot (see _migrate_entry() /
# latest_metrics()). Everything else logged for a video (pillar, concept,
# title, duration_secs, upload_date, thumb_swapped, ab_variant, ...) is
# time-invariant metadata and stays at the top level of the video's entry.
_METRIC_KEYS = (
    "views", "estimatedMinutesWatched", "averageViewDuration",
    "videoThumbnailImpressionsClickRate", "videoThumbnailImpressions",
    "likes", "comments",
)

_PILLARS = ["temporal", "activity", "emotional", "aesthetic", "cross_genre"]


class AnalyticsUnavailable(RuntimeError):
    """Analytics can't be fetched: not connected, or no channel ID."""


def _get_analytics_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not os.path.exists(TOKEN_FILE):
        raise AnalyticsUnavailable("YouTube isn't connected (token.json not found).")

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, _ANALYTICS_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtubeAnalytics", "v2", credentials=creds)


def _get_channel_id() -> str:
    """Fetch own channel ID from YouTube Data API using existing credentials."""
    cid = os.getenv("YT_CHANNEL_ID")
    if cid:
        return cid
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(TOKEN_FILE, _ANALYTICS_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds)
        resp = yt.channels().list(part="id", mine=True).execute()
        items = resp.get("items", [])
        if items:
            return items[0]["id"]
    except Exception as ex:
        print(f"[analytics] Could not fetch channel ID: {ex}")
    raise AnalyticsUnavailable("Couldn't find the channel ID. Set YT_CHANNEL_ID in .env "
                               "or reconnect YouTube.")


def fetch_video_metrics(
    svc,
    video_id: str,
    channel_id: str,
    upload_date: str,
    end_date: str,
) -> dict | None:
    """
    Query YouTube Analytics for one video. Returns metric dict or None.

    Engagement metrics (views, watch time, likes, comments) support per-video
    filtering. Reach metrics (impressions, CTR) are channel-scoped — we query
    with dimensions=video and find our video's row client-side.
    """
    result: dict = {}

    # Query 1: engagement metrics filtered to this video
    try:
        resp = svc.reports().query(
            ids=f"channel=={channel_id}",
            startDate=upload_date,
            endDate=end_date,
            metrics=METRICS_ENGAGEMENT,
            filters=f"video=={video_id}",
        ).execute()
        rows = resp.get("rows", [])
        if not rows:
            return None
        headers = [h["name"] for h in resp["columnHeaders"]]
        result.update(dict(zip(headers, rows[0])))
    except Exception as ex:
        print(f"  [analytics] {video_id}: engagement query error — {ex}")
        return None

    # Query 2: reach metrics are channel-scoped; use dimensions=video and find our row
    try:
        resp2 = svc.reports().query(
            ids=f"channel=={channel_id}",
            startDate=upload_date,
            endDate=end_date,
            metrics=METRICS_REACH,
            dimensions="video",
        ).execute()
        headers2 = [h["name"] for h in resp2.get("columnHeaders", [])]
        for row in resp2.get("rows", []):
            row_dict = dict(zip(headers2, row))
            if row_dict.get("video") == video_id:
                result.update({k: v for k, v in row_dict.items() if k != "video"})
                break
    except Exception as ex:
        print(f"  [analytics] {video_id}: reach query error (non-fatal) — {ex}")

    return result if result else None


# ── Longitudinal storage: migration + read helpers ──────────────────────────
def _is_history_format(entry: dict) -> bool:
    return isinstance(entry, dict) and isinstance(entry.get("history"), list)


def _migrate_entry(entry: dict) -> dict:
    """
    Upgrade one video's analytics_log.json entry to the longitudinal
    {"history": [snapshot, ...], **metadata} shape if it's still the old
    flat single-snapshot shape. Idempotent -- already-migrated entries pass
    through unchanged. Never raises (falls back to wrapping the entry as-is
    so a malformed old row doesn't crash the whole load).
    """
    try:
        if _is_history_format(entry):
            return entry
        snapshot = {k: entry[k] for k in _METRIC_KEYS if k in entry}
        snapshot["date"] = str(entry.get("fetched_at") or entry.get("upload_date") or "")[:10]
        if entry.get("fetched_at"):
            snapshot["fetched_at"] = entry["fetched_at"]
        metadata = {k: v for k, v in entry.items() if k not in _METRIC_KEYS}
        metadata["history"] = [snapshot] if snapshot.get("date") else []
        return metadata
    except Exception:
        return {"history": [], **(entry if isinstance(entry, dict) else {})}


def latest_metrics(entry: dict) -> dict:
    """
    Return the most recent metrics snapshot for a video's analytics entry.

    Works with both the new longitudinal {"history": [...]} format and the
    old flat single-snapshot format (which is also what unit tests pass
    directly, so this must never require migration to work) -- if `entry`
    has no "history" list, it's treated as an already-flat metrics dict.
    """
    if _is_history_format(entry):
        hist = entry.get("history") or []
        return hist[-1] if hist else {}
    return entry or {}


SCORE_AT_AGE_DAYS = 7
_RETENTION_WINDOW_SECS = 1800


def metrics_at_age(entry: dict, days: int = SCORE_AT_AGE_DAYS) -> dict:
    """The snapshot taken closest to `days` after upload, so videos of
    different ages are compared on equal footing (a 60-day-old video has
    piled up far more views than a 3-day-old one). Falls back to the latest
    snapshot when upload date or snapshot dates are missing."""
    if not _is_history_format(entry):
        return entry or {}
    hist = entry.get("history") or []
    upload = entry.get("upload_date", "")
    try:
        target = (datetime.datetime.fromisoformat(upload[:10])
                  + datetime.timedelta(days=days)).date()
    except ValueError:
        return hist[-1] if hist else {}
    dated = []
    for snap in hist:
        try:
            dated.append((abs((datetime.date.fromisoformat(snap.get("date", "")[:10]) - target).days), snap))
        except ValueError:
            continue
    if not dated:
        return hist[-1] if hist else {}
    return min(dated, key=lambda d: d[0])[1]


def ctr_fraction(value) -> float | None:
    """Click-through rate as a fraction. Accepts either convention the API
    might use (0.045 or 4.5 for 4.5%), so a unit mismatch can't silently pin
    every CTR at 100%."""
    if value is None:
        return None
    v = float(value)
    return v / 100.0 if v > 1.0 else v


def _load_raw_analytics() -> dict:
    if not os.path.exists(ANALYTICS_LOG):
        return {}
    try:
        with open(ANALYTICS_LOG) as f:
            return json.load(f)
    except Exception:
        return {}


def load_analytics() -> dict:
    """
    Load assets/analytics_log.json, migrating any old flat-format entries to
    the new longitudinal {"history": [...]} shape in memory (the file itself
    is only rewritten by sync_analytics()/swap_low_ctr_thumbnails(), so a
    read-only call never touches disk). Returns {} if missing/unreadable.
    """
    raw = _load_raw_analytics()
    return {vid: _migrate_entry(e) for vid, e in raw.items()}


def load_analytics_history() -> dict[str, list[dict]]:
    """{video_id: [snapshot, ...]} — the full longitudinal series per video,
    sorted oldest-first. Used by the cohort/growth chart, CUSUM change-point
    detection, and forecasting."""
    analytics = load_analytics()
    out = {}
    for vid, entry in analytics.items():
        hist = sorted(entry.get("history") or [], key=lambda s: s.get("date", ""))
        out[vid] = hist
    return out


def sync_analytics() -> dict:
    """
    Fetch analytics for all eligible uploads and append a dated snapshot to
    each video's history in analytics_log.json (append-only longitudinal
    series -- a video already being tracked gets a *new* row each sync, not
    an overwritten one, so growth/velocity can be reconstructed later).
    Re-running sync_analytics() the same day is idempotent: a video that
    already has a snapshot dated today is skipped (no duplicate row, no
    wasted API quota). Returns the full (migrated, longitudinal-format)
    analytics dict.
    """
    uploads: list[dict] = []
    if os.path.exists(UPLOAD_LOG):
        with open(UPLOAD_LOG) as f:
            uploads = json.load(f)

    analytics = load_analytics()

    now    = datetime.datetime.now(datetime.timezone.utc)
    today  = now.strftime("%Y-%m-%d")
    min_dt = now - datetime.timedelta(days=MIN_AGE_DAYS)
    max_dt = now - datetime.timedelta(days=MAX_AGE_DAYS)

    def _already_synced_today(vid: str) -> bool:
        container = analytics.get(vid)
        if not container:
            return False
        hist = container.get("history") or []
        return bool(hist) and hist[-1].get("date") == today

    eligible = [
        e for e in uploads
        if e.get("type") == "upload"
        and e.get("video_id")
        and _YT_ID_RE.match(str(e["video_id"]))
        and not _already_synced_today(e["video_id"])
        and e.get("timestamp", "")[:10] <= min_dt.strftime("%Y-%m-%d")
        and e.get("timestamp", "")[:10] >= max_dt.strftime("%Y-%m-%d")
    ]

    if not eligible:
        print("[analytics] No new eligible videos to sync.")
        return analytics

    svc        = _get_analytics_service()
    channel_id = _get_channel_id()
    updated    = 0

    for entry in eligible:
        vid         = entry["video_id"]
        upload_date = entry["timestamp"][:10]
        metrics     = fetch_video_metrics(svc, vid, channel_id, upload_date, today)
        if metrics:
            ctr   = metrics.get("videoThumbnailImpressionsClickRate", 0) or 0
            views = int(metrics.get("views", 0) or 0)

            container = analytics.get(vid)
            if container is None:
                # New video — randomized initial A/B thumbnail-variant label
                # (see swap_low_ctr_thumbnails()'s z-test-gated swap, which
                # toggles this field). Randomizing which label ("A"/"B") a
                # video starts on avoids a systematic bias where "primary
                # thumbnail" always maps to the same variant slot across the
                # whole channel history.
                container = {
                    "pillar":                entry.get("pillar"),
                    "concept":               entry.get("concept"),
                    "title":                 entry.get("title"),
                    "title_variants":        entry.get("title_variants", []),
                    "title_variant_strategies": entry.get("title_variant_strategies", []),
                    "title_chosen_idx":      entry.get("title_chosen_idx", 0),
                    "title_chosen_strategy": entry.get("title_chosen_strategy"),
                    "duration_secs":         entry.get("duration_secs"),
                    # Composition-selection feedback (sub-genre/BPM bandits --
                    # see sub_genre_weights()/bpm_bucket_weights() below):
                    # copied through the same way as
                    # pillar/duration_secs above, defaulting sensibly for
                    # older upload_log entries logged before these fields
                    # existed so a pre-existing log never breaks a sync.
                    "sub_genre":             entry.get("sub_genre", ""),
                    "bpm":                   entry.get("bpm"),
                    "music_engine":          entry.get("music_engine", "v1"),
                    "upload_date":      upload_date,
                    "ab_variant":       random.choice(["A", "B"]),
                    "history":          [],
                }
                analytics[vid] = container

            snapshot = {
                **{k: v for k, v in metrics.items() if k in _METRIC_KEYS},
                "date":       today,
                "fetched_at": now.isoformat(),
            }
            container["history"].append(snapshot)

            updated += 1
            print(f"  {vid}  CTR={ctr:.2%}  views={views}  pillar={entry.get('pillar', '?')}")

    from scripts.fileutil import atomic_write_json, preserve_if_corrupt
    preserve_if_corrupt(ANALYTICS_LOG)
    atomic_write_json(ANALYTICS_LOG, analytics, ensure_ascii=False)

    print(f"[analytics] synced {updated} video(s). total tracked: {len(analytics)}")
    return analytics


def compute_pillar_stats(analytics: dict) -> dict:
    """
    Pure computation (no printing) so both the CLI report() and the webui
    Analytics view can consume it. Returns:
      {"by_pillar": [{"pillar", "avg_ctr", "avg_views", "avg_watch_min", "n",
                       "marker"}, ...] sorted best-CTR-first,
       "channel_avg_ctr": float, "n_total": int}
    """
    from collections import defaultdict
    by_pillar: dict[str, list] = defaultdict(list)
    for data in analytics.values():
        m   = latest_metrics(data)
        p   = data.get("pillar") or "unknown"
        ctr = m.get("videoThumbnailImpressionsClickRate")
        wt  = m.get("estimatedMinutesWatched")
        v   = m.get("views")
        if ctr is not None:
            by_pillar[p].append((float(ctr), float(wt or 0), float(v or 0)))

    all_ctrs = [c for rows in by_pillar.values() for c, _, _ in rows]
    channel_avg = sum(all_ctrs) / len(all_ctrs) if all_ctrs else 0

    rows_out = []
    for pillar, rows in sorted(by_pillar.items(), key=lambda x: -sum(c for c, _, __ in x[1]) / len(x[1])):
        avg_ctr = sum(c for c, _, __ in rows) / len(rows)
        avg_views = sum(v for _, __, v in rows) / len(rows)
        avg_wt = sum(w for _, w, __ in rows) / len(rows)
        marker = "▲" if avg_ctr > channel_avg * 1.1 else ("▼" if avg_ctr < channel_avg * 0.9 else " ")
        rows_out.append({
            "pillar": pillar, "avg_ctr": avg_ctr, "avg_views": avg_views,
            "avg_watch_min": avg_wt, "n": len(rows), "marker": marker,
        })

    return {"by_pillar": rows_out, "channel_avg_ctr": channel_avg, "n_total": len(all_ctrs)}


def playlist_stats(analytics: dict, env: dict | None = None) -> list[dict]:
    """
    Aggregate the same per-video CTR/views/watch-time data compute_pillar_stats()
    uses, but grouped by the playlist each video would resolve to via
    scripts/playlist_curation.py's pillar -> env-var -> playlist-ID mapping
    (resolve_playlist_id) rather than by raw pillar name. Reuses that module's
    mapping logic instead of re-deriving which env var backs which pillar --
    see its docstring for the full priority order (pillar-specific env var,
    then the legacy duration-based fallback, then unassigned).

    Returns [{"playlist_id", "pillars", "avg_ctr", "avg_views",
              "avg_watch_min", "n"}, ...] sorted by avg_views desc. Videos
    that don't resolve to any configured playlist ID are grouped under
    playlist_id=None ("Unassigned").

    `env` defaults to os.environ; pass a plain dict in tests instead of
    mutating process environment (same convention as resolve_playlist_id).
    """
    from collections import defaultdict

    from scripts.playlist_curation import resolve_playlist_id

    by_playlist: dict[str | None, list] = defaultdict(list)
    pillars_seen: dict[str | None, set] = defaultdict(set)

    for data in analytics.values():
        m = latest_metrics(data)
        ctr = m.get("videoThumbnailImpressionsClickRate")
        if ctr is None:
            continue
        wt = m.get("estimatedMinutesWatched")
        v = m.get("views")
        pillar = data.get("pillar") or "unknown"
        seo_like = {"pillar": pillar, "duration": data.get("duration") or ""}
        playlist_id = resolve_playlist_id(seo_like, env)
        by_playlist[playlist_id].append((float(ctr), float(wt or 0), float(v or 0)))
        pillars_seen[playlist_id].add(pillar)

    rows_out = []
    for playlist_id, rows in by_playlist.items():
        avg_ctr = sum(c for c, _, __ in rows) / len(rows)
        avg_views = sum(v for _, __, v in rows) / len(rows)
        avg_wt = sum(w for _, w, __ in rows) / len(rows)
        rows_out.append({
            "playlist_id": playlist_id,
            "pillars": sorted(pillars_seen[playlist_id]),
            "avg_ctr": avg_ctr, "avg_views": avg_views,
            "avg_watch_min": avg_wt, "n": len(rows),
        })
    rows_out.sort(key=lambda r: -r["avg_views"])
    return rows_out


# ── Composite engagement score (feeds bandit binarization) ─────────────────
def composite_engagement_score(entry: dict, duration_secs: float | None = None) -> float | None:
    """
    Weighted composite KPI combining four engagement signals into one score
    in [0, 1] -- used as the bandit's success/failure binarization input
    (see _bandit_weights()) instead of raw CTR alone, since CTR only rewards
    a clicky thumbnail/title and says nothing about whether the video then
    actually held attention or drove real interaction.

    Weights (retention-first, since that's what YouTube's own recommender
    leans on most heavily; CTR next since it's still the biggest lever this
    channel directly controls via titles/thumbnails; likes/comments last as
    lower-volume, noisier signals):
        watch_ratio   0.40   averageViewDuration / duration_secs
        ctr           0.35   videoThumbnailImpressionsClickRate
        like_rate     0.15   likes / views
        comment_rate  0.10   comments / views

    Any component whose inputs aren't available is dropped and the
    remaining weights are renormalized to sum to 1.0 -- this degrades
    gracefully for older logged entries that predate like/comment tracking,
    or callers that only have CTR (e.g. title_variant_weights()). Returns
    None if *no* component has usable data.
    """
    m = metrics_at_age(entry)
    duration_secs = duration_secs or entry.get("duration_secs")
    views = m.get("views")

    components: list[tuple[float, float]] = []  # (weight, value in [0,1])

    avd = m.get("averageViewDuration")
    if avd is not None and duration_secs:
        try:
            # Retention against the first 30 minutes, not the whole video:
            # dividing by the full length scored every 8-hour video near zero
            # however well it held viewers, biasing every bandit to short ones.
            watch_ratio = max(0.0, min(1.0, float(avd) / min(float(duration_secs), _RETENTION_WINDOW_SECS)))
            components.append((0.40, watch_ratio))
        except (TypeError, ZeroDivisionError):
            pass

    ctr = ctr_fraction(m.get("videoThumbnailImpressionsClickRate"))
    if ctr is not None:
        components.append((0.35, max(0.0, min(1.0, ctr))))

    likes = m.get("likes")
    if likes is not None and views:
        try:
            components.append((0.15, max(0.0, min(1.0, float(likes) / float(views)))))
        except (TypeError, ZeroDivisionError):
            pass

    comments = m.get("comments")
    if comments is not None and views:
        try:
            components.append((0.10, max(0.0, min(1.0, float(comments) / float(views)))))
        except (TypeError, ZeroDivisionError):
            pass

    if not components:
        return None
    total_w = sum(w for w, _ in components)
    return sum(w * v for w, v in components) / total_w


def _build_bucket_bandit(buckets: dict[str, list[float]]) -> ThompsonSamplingBandit:
    """
    Build a Beta-Bernoulli bandit (scripts/bandit.py) with
    one arm per bucket label, updated from `buckets` ({label: [scores]})
    binarized against the *pooled* median across all buckets (a
    median split: one bucket's own median would call half of every bucket
    a "win"). Shared by _bandit_weights() (derives the weight multiplier)
    and pillar_bandit_posteriors() (exposes the raw posterior for the
    dashboard). Every label in `buckets` becomes an arm even if its value
    list is empty (starts at the uninformative Beta(1,1) prior).
    """
    bandit = ThompsonSamplingBandit(list(buckets.keys()))
    all_vals = [x for rows in buckets.values() for x in rows]
    if not all_vals:
        return bandit
    median = statistics.median(all_vals)
    for label, rows in buckets.items():
        successes = sum(1 for x in rows if x >= median)
        failures = len(rows) - successes
        bandit.update_counts(label, successes, failures)
    return bandit


def _bandit_weights(buckets: dict[str, list[float]], min_samples: int = 5) -> dict[str, float] | None:
    """
    Shared bandit-backed weight computation used by pillar_weights(),
    duration_weights(), and title_variant_weights().

    `buckets` is {arm_label: [composite_score_or_ctr, ...]} built by the
    caller (one value per observed video/variant) and fed to
    _build_bucket_bandit(). The returned weight for each arm with
    >= min_samples observations is its posterior mean normalized against
    the channel-pooled posterior mean (one combined arm over every
    observation, so it's weighted by sample size rather than a naive
    average-of-arm-means), clamped to [0.5, 2.0] — the same output contract
    and clamp range the old raw-mean-ratio multiplier had, so callers
    (duration_weights() / title_variant_weights() / pillar_weights()) don't
    need to change, but it's now backed by a real Bayesian posterior instead
    of a noisy small-sample mean ratio.

    Arms with fewer than min_samples observations are omitted from the
    returned dict (caller keeps its own neutral 1.0 default for those).
    Returns None if *no* arm has reached min_samples yet.
    """
    if not any(len(v) >= min_samples for v in buckets.values()):
        return None

    bandit = _build_bucket_bandit(buckets)

    total_successes = sum(bandit.alpha[a] - 1.0 for a in bandit.arms)
    total_failures = sum(bandit.beta[a] - 1.0 for a in bandit.arms)
    # Channel-pooled posterior: one combined arm over every observation, used
    # as the normalization baseline (naturally sample-size-weighted, unlike
    # a flat average of each arm's own posterior mean).
    channel_alpha = 1.0 + total_successes
    channel_beta = 1.0 + total_failures
    pooled_mean = channel_alpha / (channel_alpha + channel_beta)
    if pooled_mean <= 0:
        return None

    weights: dict[str, float] = {}
    for label, rows in buckets.items():
        if len(rows) >= min_samples:
            ratio = bandit.posterior_mean(label) / pooled_mean
            weights[label] = max(0.5, min(2.0, ratio))
    return weights


def pillar_bandit_posteriors(pillars: list[str] | None = None, analytics: dict | None = None) -> dict:
    """
    {pillar: {alpha, beta, n, mean}} — the raw Beta-Bernoulli posterior
    behind pillar_weights(), exposed separately for the webui Analytics
    page's bandit-posterior panel (shows the actual alpha/beta/sample-count
    a viewer can sanity-check, not just the derived weight multiplier).
    Every requested pillar is included even with zero samples (starts at
    the uninformative Beta(1,1) prior, mean 0.5).
    """
    pillars = list(pillars or _PILLARS)
    if analytics is None:
        analytics = load_analytics()

    from collections import defaultdict as _dd
    by_pillar: dict[str, list[float]] = _dd(list)
    for entry in (analytics or {}).values():
        p = entry.get("pillar")
        if p not in pillars:
            continue
        score = composite_engagement_score(entry)
        if score is None:
            continue
        by_pillar[p].append(score)

    buckets = {p: by_pillar.get(p, []) for p in pillars}
    return _build_bucket_bandit(buckets).posterior_stats()


def title_variant_weights(analytics: dict | None = None) -> dict[str, dict[str, float]]:
    """
    Per-pillar weights for title HOOK STRATEGIES (see generate_seo.py's
    HOOK_STRATEGIES: "scene", "moment", "radio"), same
    0.5x-2.0x/>=5-samples pattern, bandit-backed (see _bandit_weights())
    using composite_engagement_score() (falls back to CTR-only when that's
    all a logged entry has, which is the common case for older rows).

    Returns {pillar: {strategy: weight}} -- keyed by hook-strategy IDENTITY
    (which creative hook family won), not by raw title_variants[] slot
    position. generate_title_variants() always builds slot i from a
    specific hook family, so a naive positional key was really only ever
    learning "which slot index tends to get clicked" -- keying by the
    strategy name itself makes the bandit learn something creatively
    meaningful ("the moment form outperforms the scene form for the 'emotional'
    pillar"), which also survives generate_title_variants() reordering or
    resizing its variant slots in the future. Callers should fall back to
    1.0 for any strategy not present in the returned per-pillar dict (no
    performance data yet).

    Rows from retired title forms (strategy names no longer in
    HOOK_STRATEGIES, or old rows with only title_chosen_idx) are skipped:
    they measured titles the current forms don't produce.
    """
    if analytics is None:
        analytics = load_analytics()
    if not analytics:
        return {}

    from scripts.generate_seo import HOOK_STRATEGIES

    from collections import defaultdict as _dd
    by_pillar_strategy: dict[str, dict[str, list[float]]] = _dd(lambda: _dd(list))
    for entry in analytics.values():
        pillar = entry.get("pillar")
        if not pillar:
            continue

        # Only the current title forms. Rows from retired forms (or old rows
        # with just an index) describe titles these forms never produce.
        strategy = entry.get("title_chosen_strategy")
        if strategy not in HOOK_STRATEGIES:
            continue

        score = composite_engagement_score(entry)
        if score is None:
            continue
        by_pillar_strategy[pillar][strategy].append(score)

    result: dict[str, dict[str, float]] = {}
    for pillar, strategy_rows in by_pillar_strategy.items():
        all_scores = [c for rows in strategy_rows.values() for c in rows]
        if len(all_scores) < 5:
            continue
        bandit_weights = _bandit_weights(dict(strategy_rows), min_samples=5)
        if bandit_weights:
            result[pillar] = bandit_weights
    return result


_TITLE_BENEFIT_VOCAB = {"study", "focus", "relax", "sleep", "chill", "unwind"}


_SEASON_TITLE_WORDS = ("winter", "snow", "frost", "cocoa", "spring", "blossom", "petals",
                       "sakura", "summer", "autumn", "leaves", "maple", "october", "sweater")
_TIME_TITLE_WORDS = ("midnight", "2am", "3am", "late at night", "morning", "afternoon",
                     "golden hour", "sunset", "dusk", "dawn", "sunrise")


def title_features(title: str) -> dict[str, str]:
    """Bucket a title string into a few coarse, cheap surface-text features
    -- feeds title_feature_weights()/title_feature_bandit_posteriors() below,
    which let the bandit learn from actual title *wording* (length/emoji/
    benefit-list-shape) instead of only which hook-strategy family was used
    (see title_variant_weights()). Buckets, not raw values, so the bandit
    keeps a small, stable arm set per dimension instead of one arm per
    unique title. Public (no leading underscore) because generate_seo.py's
    generate_seo() also calls this directly to bucket each unpublished title
    candidate before applying title_feature_weights() to it.
    """
    length = len(title)
    length_bucket = ("short_lt45" if length < 45 else
                      "target_45_70" if length <= 70 else "long_gt70")
    has_emoji = any(ord(c) > 0x2600 for c in title)
    benefit_hits = sum(1 for w in _TITLE_BENEFIT_VOCAB if w in title.lower())
    low = title.lower()
    return {
        "length_bucket": length_bucket,
        "has_emoji": "emoji" if has_emoji else "no_emoji",
        "benefit_list": "benefit_list" if benefit_hits >= 2 else "no_benefit_list",
        # The dimensions above describe the retired title templates (every
        # current title has an emoji and none lists benefits); these vary
        # between current titles. Old rows simply score into them too.
        "length_band": ("under_40" if length < 40 else "40_62" if length <= 62 else "over_62"),
        "seasonal": "seasonal" if any(w in low for w in _SEASON_TITLE_WORDS) else "evergreen",
        "time_of_day": "time" if any(w in low for w in _TIME_TITLE_WORDS) else "no_time",
    }


def _title_feature_buckets(analytics: dict | None) -> dict[str, dict[str, list[float]]]:
    """{feature_dim: {bucket: [scores]}} over every logged video's actual
    published `title` -- shared by title_feature_weights() and
    title_feature_bandit_posteriors() below. Only the CHOSEN title is logged
    per video (same as title_variant_weights()'s inputs), so this mines the
    same already-logged text, not new data collection.
    """
    if analytics is None:
        analytics = load_analytics()
    from collections import defaultdict as _dd
    by_dim: dict[str, dict[str, list[float]]] = _dd(lambda: _dd(list))
    for entry in (analytics or {}).values():
        title = entry.get("title")
        if not title:
            continue
        score = composite_engagement_score(entry)
        if score is None:
            continue
        for dim, bucket in title_features(title).items():
            by_dim[dim][bucket].append(score)
    return by_dim


def title_feature_weights(analytics: dict | None = None) -> dict[str, dict[str, float]]:
    """
    {feature_dim: {bucket: weight}} -- same 0.5x-2.0x/>=5-samples bandit
    pattern as title_variant_weights(), but keyed by surface-text features
    mined from the already-logged `title` field (see title_features())
    instead of hook-strategy identity. title_variant_weights() only ever
    learns "which of the 3 named hook families wins"; this mines the same
    logged title text for finer-grained signal: does a target-length title
    outperform a long one, does an emoji help, does the benefit-list
    phrasing actually work.

    Returns {} if analytics_log.json has no entries with usable data yet
    (e.g. a brand new channel) -- callers should fall back to 1.0 per bucket.
    """
    result: dict[str, dict[str, float]] = {}
    for dim, buckets in _title_feature_buckets(analytics).items():
        weights = _bandit_weights(dict(buckets), min_samples=5)
        if weights:
            result[dim] = weights
    return result


def title_feature_bandit_posteriors(analytics: dict | None = None) -> dict:
    """
    {feature_dim: {bucket: {alpha, beta, n, mean}}} -- the raw posteriors
    behind title_feature_weights(), for the webui Analytics page's
    "Title-feature bandit posteriors" panel (mirrors
    pillar_bandit_posteriors()). Unlike pillar_bandit_posteriors(), the
    dim/bucket universe isn't a small fixed list passed in by the caller --
    it's whatever title_features() actually produced for the logged
    titles, so this can return {} (not a zero-sample-per-arm dict) when
    analytics_log.json has no title data yet.
    """
    return {
        dim: _build_bucket_bandit(buckets).posterior_stats()
        for dim, buckets in _title_feature_buckets(analytics).items()
    }


def pillar_weights(pillars: list[str] | None = None, analytics: dict | None = None) -> dict[str, float]:
    """
    Per-pillar weight multipliers (0.5x-2.0x), bandit-backed (see
    _bandit_weights()) using composite_engagement_score(). This is the
    analytics.py-native implementation behind generate_seo.py's
    _pillar_weights() thin wrapper -- kept here so all three weighting
    functions (this one, duration_weights(), title_variant_weights()) share
    one binarization + posterior-ratio implementation instead of three
    hand-rolled copies.

    Note vs. the old generate_seo.py implementation: a pillar with *zero*
    observed samples now stays at the neutral default of 1.0 rather than
    being pulled down to the 0.5 floor (which was an artifact of the old
    code always computing avgs[p]/channel_avg = 0/channel_avg for
    no-data pillars, not an intentional penalty) -- an arm the bandit has
    never seen shouldn't be treated as a *proven* underperformer.
    """
    pillars = list(pillars or _PILLARS)
    default = {p: 1.0 for p in pillars}
    if analytics is None:
        analytics = load_analytics()
    if not analytics:
        return default

    from collections import defaultdict as _dd
    by_pillar: dict[str, list[float]] = _dd(list)
    for entry in analytics.values():
        p = entry.get("pillar")
        if p not in pillars:
            continue
        score = composite_engagement_score(entry)
        if score is None:
            continue
        by_pillar[p].append(score)

    bandit_weights = _bandit_weights(by_pillar, min_samples=5)
    if bandit_weights is None:
        return default

    weights = dict(default)
    weights.update(bandit_weights)
    return weights


# ── Composition-selection feedback (sub-genre / BPM / engine bandits) ───────
# Extends the same engagement-bandit machinery above (previously wired only
# into SEO-pillar choice and video duration) to which sub-genre, BPM, and
# generation engine (v1 vs v2) get used -- see composer.py's
# _pick_subgenre_weighted()/pick_params() and run.py's engine selection for
# the call sites. All three below are thin wrappers around
# composite_engagement_score()/_bandit_weights() -- zero new statistical
# machinery, same 0.5x-2.0x clamp and >=5-samples-per-arm cold-start
# behavior as pillar_weights()/duration_weights().

def sub_genre_weights(sub_genres: list[str] | None = None, analytics: dict | None = None) -> dict[str, float]:
    """
    Per-sub-genre weight multipliers (0.5x-2.0x), bandit-backed (see
    _bandit_weights()) using composite_engagement_score() -- identical
    pattern to pillar_weights(), bucketed on entry['sub_genre'] (which
    sub-genre a track was actually generated in, e.g. "chillhop") instead of
    entry['pillar'] (the SEO framing, e.g. "temporal").

    `sub_genres` defaults to every known sub-genre key from
    scripts.composer._SUBGENRE_CONFIG -- lazy-imported HERE
    (inside the function body, not at module top) so analytics.py doesn't
    acquire a hard import-time dependency on the whole music-generation
    module (which does soundfont/filesystem setup at import time) just for
    this, its other non-composition callers (pillar/duration/title-variant
    weighting, the webui Analytics page, etc.) don't need it.
    """
    if sub_genres is None:
        try:
            from scripts.composer import _SUBGENRE_CONFIG
            sub_genres = list(_SUBGENRE_CONFIG.keys())
        except Exception:
            sub_genres = []
    sub_genres = list(sub_genres)
    default = {s: 1.0 for s in sub_genres}
    if analytics is None:
        analytics = load_analytics()
    if not analytics:
        return default

    from collections import defaultdict as _dd
    by_sub: dict[str, list[float]] = _dd(list)
    for entry in analytics.values():
        s = entry.get("sub_genre")
        if s not in sub_genres:
            continue
        score = composite_engagement_score(entry)
        if score is None:
            continue
        by_sub[s].append(score)

    bandit_weights = _bandit_weights(by_sub, min_samples=5)
    if bandit_weights is None:
        return default

    weights = dict(default)
    weights.update(bandit_weights)
    return weights


def bpm_bucket_weights(bucket_width: int = 10, analytics: dict | None = None) -> dict[int, float]:
    """
    Weight multipliers per BPM bucket (entry['bpm'] floor-divided down to
    the nearest `bucket_width`, e.g. bpm=82 -> bucket 80), bandit-backed the
    same way as duration_weights() -- 0.5x-2.0x, needs >=5 samples in a
    bucket to move off neutral.

    Unlike pillar_weights()/sub_genre_weights(), there's no fixed universe
    of bucket labels to pre-seed a neutral 1.0 default for (BPM buckets only
    exist once actually observed) -- callers should treat any bucket key
    missing from the returned dict as neutral (1.0), the same convention
    _bandit_weights() already uses for arms below the sample threshold.
    Returns {} (an empty dict, all-neutral) when there's no/insufficient
    data, same cold-start meaning as duration_weights()'s all-1.0 default.
    """
    if analytics is None:
        analytics = load_analytics()
    if not analytics:
        return {}

    from collections import defaultdict as _dd
    by_bucket: dict[int, list[float]] = _dd(list)
    for entry in analytics.values():
        bpm = entry.get("bpm")
        if not bpm:
            continue
        try:
            bucket = (int(bpm) // bucket_width) * bucket_width
        except (TypeError, ValueError):
            continue
        score = composite_engagement_score(entry)
        if score is None:
            continue
        by_bucket[bucket].append(score)

    bandit_weights = _bandit_weights(by_bucket, min_samples=5)
    return bandit_weights or {}


def report(analytics: dict | None = None) -> None:
    """Print CTR and watch time grouped by pillar, sorted best-first."""
    if analytics is None:
        if not os.path.exists(ANALYTICS_LOG):
            print("[analytics] No data. Run sync first.")
            return
        analytics = load_analytics()

    if not analytics:
        print("[analytics] No data yet.")
        return

    result = compute_pillar_stats(analytics)

    print(f"\n{'PILLAR':16s} {'AVG CTR':>8s} {'AVG VIEWS':>10s} {'AVG WATCH(min)':>15s} {'N':>4s}")
    print("─" * 58)
    for row in result["by_pillar"]:
        print(f"{row['marker']} {row['pillar']:14s} {row['avg_ctr']:>8.2%} "
              f"{row['avg_views']:>10.0f} {row['avg_watch_min']:>15.1f} {row['n']:>4d}")

    print("─" * 58)
    print(f"  {'channel avg':14s} {result['channel_avg_ctr']:>8.2%}  (n={result['n_total']})")
    print()


# ── Two-proportion z-test (thumbnail A/B significance) ──────────────────────
def two_proportion_ztest(
    successes_a: float, trials_a: float, successes_b: float, trials_b: float,
) -> tuple[float, float]:
    """
    Standard pooled two-proportion z-test, two-sided. Textbook formula (any
    intro-stats reference), not adapted from any library:

        p1 = x1/n1, p2 = x2/n2
        p_pool = (x1+x2) / (n1+n2)
        se = sqrt(p_pool * (1-p_pool) * (1/n1 + 1/n2))
        z  = (p1 - p2) / se
        p_value = 2 * P(Z > |z|)   under the standard normal (scipy.stats.norm)

    Returns (z, p_value). Degenerate inputs (zero trials, or a pooled
    proportion of exactly 0 or 1, which makes the standard error zero) return
    (0.0, 1.0) -- "not significant" -- rather than raising, since this feeds
    an automated swap decision that must never crash the analytics sync.
    """
    from scipy.stats import norm

    if trials_a <= 0 or trials_b <= 0:
        return 0.0, 1.0
    p1 = successes_a / trials_a
    p2 = successes_b / trials_b
    p_pool = (successes_a + successes_b) / (trials_a + trials_b)
    if p_pool <= 0 or p_pool >= 1:
        return 0.0, 1.0
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / trials_a + 1 / trials_b))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    p_value = 2 * norm.sf(abs(z))
    return z, p_value


def swap_low_ctr_thumbnails(analytics: dict | None = None, p_threshold: float = 0.05) -> None:
    """
    Underperformer swap -- NOT an A/B test of two thumbnails. For videos
    7-30 days old whose CTR is significantly below the rest of the channel's
    (two-proportion z-test), swap in the alternate thumbnail if one exists
    (thumb_*_alt.jpg). The comparison is against *other videos*, so it
    flags weak videos, not a weak thumbnail as such. One test runs per
    eligible video, so the threshold is Bonferroni-corrected
    (p_threshold / number of videos tested) to keep chance swaps rare.

    The test compares this video's estimated clicks/impressions against the
    pooled clicks/impressions of every *other* currently-eligible, not-yet-
    swapped video on the channel (its own two-sided z-test per video, since
    there's no pre-existing "B" impression/click data for the alt thumbnail
    to compare against -- it hasn't been shown yet). "Clicks" are estimated
    as ctr * impressions (impressions is the correct denominator CTR is
    itself defined over, so it's also the correct trial count for the
    proportion test). A swap only fires when the video's CTR is both
    significantly different (p < p_threshold) *and* below the pooled
    average -- a significantly *higher*-than-average video is left alone.

    On a swap, `ab_variant` (randomly assigned "A"/"B" the first time a video
    is synced -- see sync_analytics()) is toggled, giving the channel a
    lightweight randomized initial-variant record instead of every video
    starting from the same fixed "primary" thumbnail baseline.
    """
    # Only persist z/p diagnostics + swap state to disk when we loaded the
    # log ourselves (the normal sync-pipeline / webui "Sync now" path) --
    # callers that pass an explicit in-memory `analytics` dict (e.g. tests)
    # get their dict mutated in place but no disk write unless a swap
    # actually happened, matching the pre-existing behavior for that case.
    _own_load = analytics is None
    if analytics is None:
        if not os.path.exists(ANALYTICS_LOG):
            return
        analytics = load_analytics()

    uploads: list[dict] = []
    if os.path.exists(UPLOAD_LOG):
        with open(UPLOAD_LOG) as f:
            uploads = json.load(f)
    vid_to_entry = {e["video_id"]: e for e in uploads if e.get("video_id")}

    # Pool of (vid, ctr, impressions) for every not-yet-swapped video with
    # both CTR and impressions data -- this feeds each video's z-test
    # baseline (pool minus itself).
    pool: list[tuple[str, float, float]] = []
    for vid, d in analytics.items():
        if d.get("thumb_swapped"):
            continue
        m = latest_metrics(d)
        ctr = ctr_fraction(m.get("videoThumbnailImpressionsClickRate"))
        impressions = m.get("videoThumbnailImpressions")
        if ctr is None or not impressions:
            continue
        pool.append((vid, ctr, float(impressions)))

    if len(pool) < 2:
        print("[analytics] thumbnail swaps: 0 (not enough videos with CTR+impressions data)")
        return

    now     = datetime.datetime.now(datetime.timezone.utc)
    min_age = now - datetime.timedelta(days=7)
    max_age = now - datetime.timedelta(days=30)

    swapped = 0
    # Bonferroni: one test per video in the pool.
    corrected_threshold = p_threshold / max(1, len(pool))
    for vid, ctr, impressions in pool:
        data = analytics[vid]
        upload_date = data.get("upload_date", "")
        try:
            udt = datetime.datetime.fromisoformat(upload_date).replace(tzinfo=datetime.timezone.utc)
        except Exception:
            continue
        if not (max_age <= udt <= min_age):
            continue

        others = [(c, i) for v, c, i in pool if v != vid]
        if not others:
            continue
        trials_b = sum(i for _, i in others)
        successes_b = sum(c * i for c, i in others)
        pooled_avg_ctr = successes_b / trials_b if trials_b else 0.0

        successes_a = ctr * impressions
        z, p_value = two_proportion_ztest(successes_a, impressions, successes_b, trials_b)
        data["thumb_ab_z"] = z
        data["thumb_ab_p"] = p_value

        if p_value >= corrected_threshold or ctr >= pooled_avg_ctr:
            continue  # not significantly worse than the rest of the channel

        # Find alternate thumbnail — validate path stays within assets/.
        # Derived from the exact thumbnail filename logged at upload time
        # (thumb_file), not guessed from the video's timestamp -- the two
        # don't necessarily match (thumbnail generation happens before final
        # assembly picks its own timestamp) and thumb filenames carry a theme
        # prefix the video filename doesn't.
        entry      = vid_to_entry.get(vid, {})
        thumb_file = entry.get("thumb_file", "")
        alt_path = (os.path.join(ROOT, "assets", thumb_file.rsplit(".", 1)[0] + "_alt.jpg")
                    if thumb_file else "")

        if not alt_path:
            continue
        _assets_root = os.path.realpath(os.path.join(ROOT, "assets"))
        if not os.path.realpath(alt_path).startswith(_assets_root + os.sep):
            continue
        if not os.path.exists(alt_path):
            continue

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            creds = Credentials.from_authorized_user_file(TOKEN_FILE, _ANALYTICS_SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            yt = build("youtube", "v3", credentials=creds)
            yt.thumbnails().set(
                videoId=vid,
                media_body=MediaFileUpload(alt_path, mimetype="image/jpeg"),
            ).execute()
            data["thumb_swapped"] = True
            data["thumb_swapped_at"] = now.isoformat()
            data["ab_variant"] = "B" if data.get("ab_variant") == "A" else "A"
            swapped += 1
            print(f"  [thumb-swap] {vid}: CTR={ctr:.2%} vs pool avg={pooled_avg_ctr:.2%} "
                  f"(p={p_value:.4f}) → swapped")
        except Exception as ex:
            print(f"  [thumb-swap] {vid}: failed — {ex}")

    if _own_load or swapped:
        from scripts.fileutil import atomic_write_json, preserve_if_corrupt
        preserve_if_corrupt(ANALYTICS_LOG)
        atomic_write_json(ANALYTICS_LOG, analytics, ensure_ascii=False)
    print(f"[analytics] thumbnail swaps: {swapped}")


# ── CUSUM change-point detection (viral-moment flagging) ────────────────────
def cusum_change_points(
    values: list[float], threshold: float | None = None, drift: float | None = None,
) -> list[int]:
    """
    Two-sided CUSUM (cumulative sum control chart, Page's test) change-point
    detector over a numeric series. Textbook algorithm (E.S. Page, 1954 --
    standard in statistical process control; this implementation is
    from-scratch, not adapted from any repo):

        s_pos[i] = max(0, s_pos[i-1] + (x_i - mean0) - drift)
        s_neg[i] = min(0, s_neg[i-1] + (x_i - mean0) + drift)

    A change point is flagged whenever s_pos exceeds +threshold or s_neg
    drops below -threshold; both accumulators reset to 0 and the running
    reference mean re-baselines to the flagged value, so the detector can
    catch multiple shifts in one series instead of triggering once and going
    silent.

    If `threshold`/`drift` aren't given, they're derived from the series'
    own standard deviation using the standard SPC rule of thumb (Montgomery,
    "Introduction to Statistical Quality Control"): drift = 0.5*sigma,
    threshold = 5*sigma -- tuned to detect roughly a 1-sigma sustained shift
    while tolerating normal day-to-day noise.

    Returns a list of indices (into `values`) where a change point was
    flagged. Empty list for series shorter than 2 points or with ~zero
    variance (nothing to detect).
    """
    n = len(values)
    if n < 2:
        return []

    if threshold is None or drift is None:
        try:
            sigma = statistics.stdev(values)
        except statistics.StatisticsError:
            sigma = 0.0
        if sigma == 0:
            return []
        if drift is None:
            drift = 0.5 * sigma
        if threshold is None:
            threshold = 5.0 * sigma

    mean0 = values[0]
    s_pos = 0.0
    s_neg = 0.0
    change_points: list[int] = []
    for i in range(1, n):
        diff = values[i] - mean0
        s_pos = max(0.0, s_pos + diff - drift)
        s_neg = min(0.0, s_neg + diff + drift)
        if s_pos > threshold or -s_neg > threshold:
            change_points.append(i)
            s_pos = 0.0
            s_neg = 0.0
            mean0 = values[i]
    return change_points


def _view_velocity(history: list[dict]) -> list[dict]:
    """[{date, velocity}] daily views-gained-per-day between consecutive
    snapshots of a video's (date, views)-sorted history. Guards against
    same-day/duplicate-date snapshots (skipped, would divide by ~0 days)."""
    snaps = sorted(
        (h for h in history if h.get("views") is not None and h.get("date")),
        key=lambda h: h["date"],
    )
    out = []
    for prev, cur in zip(snaps, snaps[1:]):
        try:
            d0 = datetime.date.fromisoformat(prev["date"])
            d1 = datetime.date.fromisoformat(cur["date"])
        except ValueError:
            continue
        days = (d1 - d0).days
        if days <= 0:
            continue
        velocity = (float(cur["views"]) - float(prev["views"])) / days
        out.append({"date": cur["date"], "velocity": velocity})
    return out


def detect_viral_moment(history: list[dict]) -> dict | None:
    """
    Run CUSUM change-point detection over a video's view-velocity series
    (derived from its longitudinal history — see _view_velocity()) to flag a
    "viral moment": a sustained shift in how fast the video is gaining
    views. Returns None if there's not enough history (< 4 snapshots, i.e.
    < 3 velocity points) to say anything meaningful, or if no change point
    is detected. Otherwise:
        {"flagged": True, "change_point_date": str, "direction": "up"|"down",
         "velocity_before": float, "velocity_after": float}
    using the *last* detected change point (most recent shift).
    """
    velocities = _view_velocity(history)
    if len(velocities) < 3:
        return None

    series = [v["velocity"] for v in velocities]
    change_points = cusum_change_points(series)
    if not change_points:
        return None

    idx = change_points[-1]
    before = series[:idx]
    after = series[idx:]
    v_before = sum(before) / len(before) if before else series[idx]
    v_after = sum(after) / len(after) if after else series[idx]
    return {
        "flagged": True,
        "change_point_date": velocities[idx]["date"],
        "direction": "up" if v_after >= v_before else "down",
        "velocity_before": v_before,
        "velocity_after": v_after,
    }


# ── Forecasting (simple exponential smoothing on view-velocity) ─────────────
def forecast_views(
    history: list[dict], horizon_days: tuple[int, ...] = (7, 30), min_points: int = 4,
) -> dict | None:
    """
    Project a video's cumulative view count `horizon_days` ahead using
    simple exponential smoothing (_ses_level) over its view-velocity
    series (views gained per day between consecutive longitudinal
    snapshots — see _view_velocity()). SES has no trend component, so it
    forecasts a smoothed *constant* future daily velocity; that estimate is
    then projected forward linearly (current_views + velocity * days) for
    each requested horizon.

    Guards: needs at least `min_points` snapshots (fewer than that gives too
    few velocity observations for SES to fit anything meaningful) — returns
    None rather than raising on any failure, since forecasting is a
    dashboard nice-to-have that must never break the analytics page or the
    sync pipeline.
    """
    snaps = sorted(
        (h for h in history if h.get("views") is not None and h.get("date")),
        key=lambda h: h["date"],
    )
    if len(snaps) < min_points:
        return None

    velocities = _view_velocity(snaps)
    if len(velocities) < max(2, min_points - 1):
        return None

    try:
        series = [v["velocity"] for v in velocities]
        next_velocity = max(0.0, _ses_level(series))
        current_views = float(snaps[-1]["views"])
        return {
            "current_views": current_views,
            "daily_velocity_estimate": next_velocity,
            "forecast": {
                f"{h}d": current_views + next_velocity * h for h in horizon_days
            },
        }
    except Exception:
        return None


def _ses_level(series: list[float]) -> float:
    """Simple exponential smoothing: the smoothed level after the last point,
    which is SES's forecast for every future step. The smoothing factor is
    the one (on a 0.05 grid) with the smallest one-step-ahead squared error,
    as statsmodels' "estimated" fit does; it replaces that dependency."""
    best_sse, best_level = None, float(series[-1])
    for alpha in [a / 20 for a in range(1, 20)]:
        level, sse = float(series[0]), 0.0
        for x in series[1:]:
            sse += (x - level) ** 2
            level = alpha * x + (1 - alpha) * level
        if best_sse is None or sse < best_sse:
            best_sse, best_level = sse, level
    return best_level


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync YouTube Analytics for lofi_factory uploads.")
    parser.add_argument("--report",      action="store_true", help="Print CTR table by pillar")
    parser.add_argument("--swap-thumbs", action="store_true", help="Swap thumbnails for low-CTR videos")
    args = parser.parse_args()

    try:
        analytics = sync_analytics()
    except AnalyticsUnavailable as e:
        print(f"[analytics] ERROR: {e}")
        sys.exit(1)
    if args.report:
        report(analytics)
    if args.swap_thumbs:
        swap_low_ctr_thumbnails(analytics)


if __name__ == "__main__":
    main()
