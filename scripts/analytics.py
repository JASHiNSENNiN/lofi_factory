"""
analytics.py — YouTube Analytics per-video tracking and pillar performance reporting.

Fetches CTR, impressions, views, and watch time for each uploaded video after it has
had at least MIN_AGE_DAYS of data. Stores results locally in assets/analytics_log.json,
which feeds the pillar weight system in generate_seo.py.

Usage:
    python scripts/analytics.py                # sync eligible videos
    python scripts/analytics.py --report       # sync + print CTR by pillar
    python scripts/analytics.py --swap-thumbs  # sync + swap low-CTR thumbnails
"""
import argparse
import datetime
import json
import os
import re
import sys

ROOT          = os.path.join(os.path.dirname(__file__), "..")

_ANALYTICS_SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
UPLOAD_LOG    = os.path.join(ROOT, "upload_log.json")
ANALYTICS_LOG = os.path.join(ROOT, "assets", "analytics_log.json")
TOKEN_FILE    = os.path.join(ROOT, "token.json")
MIN_AGE_DAYS  = 7
MAX_AGE_DAYS  = 90   # stop tracking after 90 days (stable)

# Metrics split by query type — engagement supports per-video filter;
# reach metrics are channel-scoped and require dimensions=video.
# See fetch_video_metrics() for how these are used.
METRICS_ENGAGEMENT = "views,estimatedMinutesWatched,averageViewDuration"
METRICS_REACH      = "videoThumbnailImpressions,videoThumbnailImpressionsClickRate"


def _get_analytics_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not os.path.exists(TOKEN_FILE):
        print("[analytics] ERROR: token.json not found. Run: python scripts/upload_youtube.py --auth")
        sys.exit(1)

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
    print("[analytics] ERROR: Set YT_CHANNEL_ID in .env or ensure token has youtube.readonly scope.")
    sys.exit(1)


def fetch_video_metrics(
    svc,
    video_id: str,
    channel_id: str,
    upload_date: str,
    end_date: str,
) -> dict | None:
    """
    Query YouTube Analytics for one video. Returns metric dict or None.

    Engagement metrics (views, watch time) support per-video filtering.
    Reach metrics (impressions, CTR) are channel-scoped — we query with
    dimensions=video and find our video's row client-side.
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


def sync_analytics() -> dict:
    """
    Fetch analytics for all eligible uploads and write analytics_log.json.
    Returns the full analytics dict.
    """
    uploads: list[dict] = []
    if os.path.exists(UPLOAD_LOG):
        with open(UPLOAD_LOG) as f:
            uploads = json.load(f)

    analytics: dict = {}
    if os.path.exists(ANALYTICS_LOG):
        with open(ANALYTICS_LOG) as f:
            analytics = json.load(f)

    now    = datetime.datetime.now(datetime.timezone.utc)
    today  = now.strftime("%Y-%m-%d")
    min_dt = now - datetime.timedelta(days=MIN_AGE_DAYS)
    max_dt = now - datetime.timedelta(days=MAX_AGE_DAYS)

    eligible = [
        e for e in uploads
        if e.get("type") == "upload"
        and e.get("video_id")
        and _YT_ID_RE.match(str(e["video_id"]))
        and e["video_id"] not in analytics
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
            analytics[vid] = {
                **metrics,
                "pillar":            entry.get("pillar"),
                "concept":           entry.get("concept"),
                "title":             entry.get("title"),
                "title_variants":    entry.get("title_variants", []),
                "title_chosen_idx":  entry.get("title_chosen_idx", 0),
                "upload_date":       upload_date,
                "fetched_at":        now.isoformat(),
            }
            updated += 1
            print(f"  {vid}  CTR={ctr:.2%}  views={views}  pillar={entry.get('pillar', '?')}")

    os.makedirs(os.path.dirname(ANALYTICS_LOG), exist_ok=True)
    with open(ANALYTICS_LOG, "w") as f:
        json.dump(analytics, f, indent=2, ensure_ascii=False)

    print(f"[analytics] synced {updated} video(s). total tracked: {len(analytics)}")
    return analytics


def report(analytics: dict | None = None) -> None:
    """Print CTR and watch time grouped by pillar, sorted best-first."""
    if analytics is None:
        if not os.path.exists(ANALYTICS_LOG):
            print("[analytics] No data. Run sync first.")
            return
        with open(ANALYTICS_LOG) as f:
            analytics = json.load(f)

    if not analytics:
        print("[analytics] No data yet.")
        return

    from collections import defaultdict
    by_pillar: dict[str, list] = defaultdict(list)
    for data in analytics.values():
        p   = data.get("pillar") or "unknown"
        ctr = data.get("videoThumbnailImpressionsClickRate")
        wt  = data.get("estimatedMinutesWatched")
        v   = data.get("views")
        if ctr is not None:
            by_pillar[p].append((float(ctr), float(wt or 0), float(v or 0)))

    all_ctrs = [c for rows in by_pillar.values() for c, _, _ in rows]
    channel_avg = sum(all_ctrs) / len(all_ctrs) if all_ctrs else 0

    print(f"\n{'PILLAR':16s} {'AVG CTR':>8s} {'AVG VIEWS':>10s} {'AVG WATCH(min)':>15s} {'N':>4s}")
    print("─" * 58)
    for pillar, rows in sorted(by_pillar.items(), key=lambda x: -sum(c for c,_,__ in x[1])/len(x[1])):
        avg_ctr   = sum(c for c,_,__ in rows) / len(rows)
        avg_views = sum(v for _,__,v in rows) / len(rows)
        avg_wt    = sum(w for _,w,__ in rows) / len(rows)
        marker    = "▲" if avg_ctr > channel_avg * 1.1 else ("▼" if avg_ctr < channel_avg * 0.9 else " ")
        print(f"{marker} {pillar:14s} {avg_ctr:>8.2%} {avg_views:>10.0f} {avg_wt:>15.1f} {len(rows):>4d}")

    print("─" * 58)
    print(f"  {'channel avg':14s} {channel_avg:>8.2%}  (n={len(all_ctrs)})")
    print()


def swap_low_ctr_thumbnails(analytics: dict | None = None) -> None:
    """
    For videos 7-30 days old with CTR < 70% of channel average,
    swap in an alternate thumbnail if one exists (thumb_*_alt.jpg).
    """
    if analytics is None:
        if not os.path.exists(ANALYTICS_LOG):
            return
        with open(ANALYTICS_LOG) as f:
            analytics = json.load(f)

    uploads: list[dict] = []
    if os.path.exists(UPLOAD_LOG):
        with open(UPLOAD_LOG) as f:
            uploads = json.load(f)
    vid_to_entry = {e["video_id"]: e for e in uploads if e.get("video_id")}

    all_ctrs = [
        float(d.get("videoThumbnailImpressionsClickRate"))
        for d in analytics.values()
        if d.get("videoThumbnailImpressionsClickRate") is not None
        and not d.get("thumb_swapped")
    ]
    if not all_ctrs:
        return
    channel_avg = sum(all_ctrs) / len(all_ctrs)

    now     = datetime.datetime.now(datetime.timezone.utc)
    min_age = now - datetime.timedelta(days=7)
    max_age = now - datetime.timedelta(days=30)

    swapped = 0
    for vid, data in analytics.items():
        if data.get("thumb_swapped"):
            continue
        ctr = data.get("videoThumbnailImpressionsClickRate")
        if ctr is None or float(ctr) >= channel_avg * 0.7:
            continue
        upload_date = data.get("upload_date", "")
        try:
            udt = datetime.datetime.fromisoformat(upload_date).replace(tzinfo=datetime.timezone.utc)
        except Exception:
            continue
        if not (max_age <= udt <= min_age):
            continue

        # Find alternate thumbnail — validate path stays within assets/
        entry    = vid_to_entry.get(vid, {})
        vid_file = entry.get("video_file", "")
        ts_part  = vid_file.replace("lofi_", "").replace(".mp4", "") if vid_file else ""
        alt_path = os.path.join(ROOT, "assets", f"thumb_{ts_part}_alt.jpg") if ts_part else ""

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
            swapped += 1
            print(f"  [thumb-swap] {vid}: CTR={float(ctr):.2%} < {channel_avg:.2%} avg → swapped")
        except Exception as ex:
            print(f"  [thumb-swap] {vid}: failed — {ex}")

    if swapped:
        with open(ANALYTICS_LOG, "w") as f:
            json.dump(analytics, f, indent=2, ensure_ascii=False)
    print(f"[analytics] thumbnail swaps: {swapped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync YouTube Analytics for lofi_factory uploads.")
    parser.add_argument("--report",      action="store_true", help="Print CTR table by pillar")
    parser.add_argument("--swap-thumbs", action="store_true", help="Swap thumbnails for low-CTR videos")
    args = parser.parse_args()

    analytics = sync_analytics()
    if args.report:
        report(analytics)
    if args.swap_thumbs:
        swap_low_ctr_thumbnails(analytics)


if __name__ == "__main__":
    main()
