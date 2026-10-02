"""
upload_youtube.py
-----------------
Uploads a video to YouTube via the Data API v3.
Requires one-time OAuth2 setup (see SETUP section below).

SETUP (one time):
  1. Go to https://console.cloud.google.com
  2. Create project → Enable "YouTube Data API v3"
  3. Create OAuth 2.0 credentials (Desktop app type)
  4. Download client_secret.json → place in lofi_factory/
  5. Run: python upload_youtube.py --auth
     (opens browser, authorize, saves token.json)
  6. All future uploads use token.json automatically

Usage:
  python upload_youtube.py --video output/lofi_XYZ.mp4 --seo assets/seo_XYZ.json --thumb assets/thumb_XYZ.jpg
"""

import os
import sys
import json
import argparse
import glob

from scripts.seo_utils import trim_tags_to_budget

ROOT = os.path.join(os.path.dirname(__file__), "..")

# Load .env (stream key, channel ID)
_env = os.path.join(ROOT, ".env")
if os.path.exists(_env):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env, override=False)
    except ImportError:
        pass

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Revenue/RPM tracking (webui Settings -> "Connect monetary analytics") is a
# separate opt-in token (token_monetary.json) that can only READ analytics:
# no upload, edit or delete rights, so a leak of that file can't touch the
# channel. Never merged into SCOPES, so normal logins and the unattended
# token refresh never see an extra consent screen.
MONETARY_SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]

CLIENT_SECRET = os.path.join(ROOT, "client_secret.json")
TOKEN_FILE    = os.path.join(ROOT, "token.json")
CHANNEL_ID    = os.environ.get("YT_CHANNEL_ID", "")


def get_authenticated_service():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("[ERROR] Missing Google API libraries.")
        print("Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            from google.auth.exceptions import RefreshError
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError as e:
                # Revoked or expired grant: the token is useless now. Anything
                # else (network down, Google 5xx) is transient, and deleting
                # the token there would force a manual re-login for nothing.
                print(f"[AUTH] Token was rejected ({e}); you need to reconnect YouTube.")
                os.remove(TOKEN_FILE)
                creds = None

        if not refreshed:
            if not sys.stdin.isatty():
                # Unattended (systemd timer, web panel job): an interactive
                # login would wait forever for a browser that never comes.
                print("[ERROR] YouTube isn't connected. Connect it in the web panel "
                      "(Settings > Connect YouTube) or run this command in a terminal.")
                sys.exit(1)
            if not os.path.exists(CLIENT_SECRET):
                print(f"[ERROR] client_secret.json not found at {CLIENT_SECRET}")
                print("  Download it from Google Cloud Console > APIs > Credentials")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            # run_local_server gives a non-deprecated token that refreshes properly.
            # Over SSH: forward port 8085 first:
            #   ssh -L 8085:localhost:8085 user@yourserver
            # Then open the printed URL in your local browser.
            print("\n[AUTH] Starting local auth server on port 8085...")
            print("  If on SSH: forward the port first in a NEW terminal:")
            print("    ssh -L 8085:localhost:8085 user@yourserver")
            print("  Then open the URL that appears below.\n")
            creds = flow.run_local_server(
                port=8085,
                open_browser=False,
                prompt="consent",   # force refresh_token even if prior grant exists
                success_message="Auth complete — return to your terminal.",
            )

        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, video_path, seo, thumbnail_path=None, publish_at=None):
    """
    publish_at: optional RFC3339 UTC timestamp (e.g. "2026-05-16T20:00:00.000Z").
    When set, forces privacyStatus="private" and schedules the video to go
    public at that time (YouTube requirement for scheduled publish).
    """
    from googleapiclient.http import MediaFileUpload

    title       = seo.get("title", "lo-fi hip hop radio")[:100]
    description = seo.get("description", "")
    # YouTube rejects if all tags joined exceed 500 chars — trim longest first
    # to preserve high-intent short tags (e.g. "lofi", "study music")
    tags        = trim_tags_to_budget(list(seo.get("tags", [])), 500)

    print(f"[UPLOAD] Uploading: {os.path.basename(video_path)}")
    print(f"  Title: {title}")

    made_for_kids = seo.get("made_for_kids", False)
    if made_for_kids:
        print("[WARN] made_for_kids=True detected — this disables monetization! Set to False unless legally required.")

    privacy = "private" if publish_at else seo.get("privacy", "public")
    if publish_at:
        print(f"  Scheduled: publishes at {publish_at} (UTC)")

    body = {
        "snippet": {
            "title": title,
            "description": description[:4900],   # YouTube hard limit is 5000 chars
            "tags": tags,
            "categoryId": seo.get("category_id", "10"),
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "madeForKids": made_for_kids,
            **({"publishAt": publish_at} if publish_at else {}),
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 50,  # 50 MB chunks — fewer token refreshes needed
    )

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print("  Uploading (this may take a while)...")
    import time
    from googleapiclient.errors import HttpError

    response = None
    retries  = 0
    tags_fallback_used = False
    while response is None:
        try:
            status, response = request.next_chunk()
            retries = 0
            if status:
                pct = int(status.progress() * 100)
                mb  = int(status.resumable_progress / 1024 / 1024)
                print(f"  Progress: {pct}%  ({mb} MB)", end="\r")
        except Exception as e:
            # A 4xx here (bad request/rejected field/permission) means the
            # request itself is invalid -- identical retries can only ever
            # fail identically, so blindly retrying it 5x with backoff (as
            # this loop used to) just burns ~1 minute guaranteed-failing
            # before giving up. Confirmed 2026-08-13: an invalidTags 400
            # did exactly this. Reserve the retry/backoff loop below for
            # genuinely transient errors (network blips, 5xx, timeouts).
            status_code = getattr(getattr(e, "resp", None), "status", None)
            if isinstance(e, HttpError) and status_code is not None and 400 <= status_code < 500:
                body_text = str(getattr(e, "content", b"")) + str(e)
                if not tags_fallback_used and "invalidTags" in body_text and body.get("snippet", {}).get("tags"):
                    # One-shot fallback: this shouldn't happen anymore now that
                    # generate_seo.py caps individual tag length before it gets
                    # here, but if some other tag source ever slips one past
                    # that, drop tags entirely (title/description still carry
                    # the SEO value) and retry once rather than losing the
                    # whole finished render over a metadata field.
                    print(f"\n  Upload error (invalidTags) — retrying once with tags "
                          f"dropped (was {len(body['snippet']['tags'])} tags)...")
                    body["snippet"]["tags"] = []
                    tags_fallback_used = True
                    request = youtube.videos().insert(
                        part="snippet,status", body=body, media_body=media)
                    continue
                raise RuntimeError(
                    f"Upload rejected ({status_code}): {e} — not retrying, "
                    f"this is a permanent request error, not a transient one."
                ) from e
            retries += 1
            if retries > 5:
                raise RuntimeError(f"Upload failed after 5 retries: {e}") from e
            wait = 2 ** retries
            print(f"\n  Upload error ({e}) — retry {retries}/5 in {wait}s...")
            time.sleep(wait)

    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\n  Uploaded! Video ID: {video_id}")
    print(f"  URL: {video_url}")

    # Set thumbnail
    if thumbnail_path and os.path.exists(thumbnail_path):
        print(f"  Setting thumbnail: {os.path.basename(thumbnail_path)}")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
        ).execute()
        print("  Thumbnail set.")

    # Auto-add to playlist (reads YT_PLAYLIST_STUDY / YT_PLAYLIST_SLEEP from env)
    _add_to_playlist(youtube, video_id, seo)

    return video_id, video_url


def _add_to_playlist(youtube, video_id: str, seo: dict):
    """Add the video to its genre playlist (opt-in, YT_GENRE_PLAYLISTS=1) and
    to the playlist configured for its pillar, if any. See
    scripts/playlist_curation.py."""
    from scripts.generate_seo import search_phrase
    from scripts.playlist_curation import genre_playlist_id, resolve_playlist_id
    targets = []
    try:
        if seo.get("genre_label"):
            targets.append(genre_playlist_id(youtube, search_phrase(seo["genre_label"])))
    except Exception as e:
        print(f"  [WARN] Genre playlist lookup failed: {e}")
    targets.append(resolve_playlist_id(seo))
    for playlist_id in dict.fromkeys(t for t in targets if t):
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={"snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }},
            ).execute()
            print(f"  Added to playlist {playlist_id}")
        except Exception as e:
            print(f"  [WARN] Playlist add failed: {e}")


def find_latest(directory, pattern):
    files = sorted(glob.glob(os.path.join(directory, pattern)), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true", help="Run auth flow only")
    parser.add_argument("--video", help="Path to video file (defaults to latest in output/)")
    parser.add_argument("--seo", help="Path to SEO JSON (defaults to latest in assets/)")
    parser.add_argument("--thumb", help="Path to thumbnail (defaults to latest in assets/)")
    args = parser.parse_args()

    youtube = get_authenticated_service()

    if args.auth:
        # Verify we're authenticated against the right channel
        try:
            ch = youtube.channels().list(part="snippet", mine=True).execute()
            items = ch.get("items", [])
            if items:
                c = items[0]
                name = c["snippet"]["title"]
                cid  = c["id"]
                print(f"[AUTH] Authenticated as: {name}")
                print(f"  Channel ID: {cid}")
                if CHANNEL_ID and cid != CHANNEL_ID:
                    print(f"  WARNING: Expected channel {CHANNEL_ID} but got {cid}")
                else:
                    print("  Channel ID matches .env ✓")
        except Exception as e:
            print(f"[AUTH] Auth OK but channel check failed: {e}")
        print("[AUTH] token.json saved. Ready to upload.")
        return

    # Auto-pick latest files if not specified
    video_path = args.video or find_latest(os.path.join(ROOT, "output"), "lofi_*.mp4")
    seo_path = args.seo or find_latest(os.path.join(ROOT, "assets"), "seo_*.json")
    thumb_path = args.thumb or find_latest(os.path.join(ROOT, "assets"), "thumb_*.jpg")

    if not video_path:
        print("[ERROR] No video found. Run the pipeline first: python run.py")
        sys.exit(1)
    if not seo_path:
        print("[ERROR] No SEO file found. Run: python scripts/generate_seo.py")
        sys.exit(1)

    with open(seo_path) as f:
        seo = json.load(f)

    video_id, url = upload_video(youtube, video_path, seo, thumb_path)

    # Log upload
    import datetime as _dt
    from scripts.fileutil import append_json_list
    append_json_list(os.path.join(ROOT, "upload_log.json"), {
        "type":             "upload",
        "video_id":         video_id,
        "url":              url,
        "title":                    seo.get("title", ""),
        "title_variants":           seo.get("title_variants", [seo.get("title", "")]),
        "title_variant_strategies": seo.get("title_variant_strategies", []),
        "title_chosen_idx":         seo.get("title_chosen_idx", 0),
        "title_chosen_strategy":    seo.get("title_chosen_strategy"),
        "pillar":           seo.get("pillar", ""),
        "concept":          seo.get("concept", ""),
        "seo_ref":          seo.get("ref_id", ""),
        "video_file":       os.path.basename(video_path),
        # Composition-selection feedback (which sub-genre/BPM/generation
        # engine got used) — see scripts/analytics.py's sub_genre_weights()/
        # bpm_bucket_weights(). Defaults keep this log-append
        # from crashing on an older-format `seo` dict that predates these
        # fields (e.g. a seo_*.json file generated before this feature).
        "sub_genre":        seo.get("sub_genre", ""),
        "bpm":              seo.get("bpm"),
        "music_engine":     seo.get("music_engine") or "v1",
        "timestamp":        _dt.datetime.now(_dt.timezone.utc).isoformat(),
    })

    print(f"\n[DONE] {url}")


if __name__ == "__main__":
    main()
