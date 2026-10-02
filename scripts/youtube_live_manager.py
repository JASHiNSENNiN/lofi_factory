"""
youtube_live_manager.py — YouTube Live Streaming API for Lo-Fi Factory
=======================================================================
Manages the full broadcast lifecycle so the stream actually shows up on the channel:

  1. Auth (reuses token.json from upload_youtube.py OAuth setup)
  2. Find existing ready/created broadcast OR create a new one
  3. Create ingestion stream → get RTMP address + key
  4. Bind broadcast to stream
  5. After ffmpeg connects, poll stream health → transition broadcast to LIVE
  6. Update broadcast title when track changes (rate-limited to ≤1 per 5 min)
  7. End broadcast on Ctrl+C (transitions to 'complete')

Falls back to env-var YT_STREAM_KEY if credentials not available.

Auth setup (one time):
  python scripts/upload_youtube.py --auth
"""

import os
import time
import datetime
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from scripts.upload_youtube import SCOPES  # noqa: E402  (one definition project-wide)
CLIENT_SECRET = os.path.join(ROOT, "client_secret.json")
TOKEN_FILE    = os.path.join(ROOT, "token.json")

_POLL_INTERVAL      = 5    # seconds between stream-health polls
_TRANSITION_TIMEOUT = 120  # give up transitioning after 2 min
# Each title update costs ~51 quota units (a 1-unit read plus a 50-unit
# update) out of a default 10,000/day that the daily upload, thumbnails and
# analytics also need. Every 30 min is at most 48 updates = ~2,450 units/day.
_TITLE_COOLDOWN     = 1800


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_youtube_service():
    """
    Return authenticated YouTube v3 service, or None if credentials unavailable.
    Never prompts interactively — only uses an existing valid/refreshable token.
    To create token.json run:  python scripts/upload_youtube.py --auth
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("  [yt-api] google-api-python-client not installed — live API disabled")
        print("           pip install google-api-python-client google-auth-oauthlib")
        return None

    if not os.path.exists(TOKEN_FILE):
        print("  [yt-api] token.json not found — falling back to stream key")
        print("           To enable broadcast management: python scripts/upload_youtube.py --auth")
        return None

    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    except Exception:
        print("  [yt-api] token.json unreadable — falling back to stream key")
        return None

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w") as fh:
                    fh.write(creds.to_json())
            except Exception as e:
                print(f"  [yt-api] Token refresh failed: {e} — falling back to stream key")
                return None
        else:
            print("  [yt-api] Token invalid — re-run: python scripts/upload_youtube.py --auth")
            return None

    try:
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"  [yt-api] Failed to build service: {e}")
        return None


# ── Broadcast lookup ──────────────────────────────────────────────────────────

def _find_broadcast(youtube, status):
    """Return first broadcast in given status string, or None."""
    try:
        resp = youtube.liveBroadcasts().list(
            part="id,snippet,status,contentDetails",
            broadcastStatus=status,
            maxResults=5,
        ).execute()
        items = resp.get("items", [])
        if items:
            return items[0]
    except Exception as e:
        print(f"  [yt-api] Error listing {status} broadcasts: {e}")
    return None


def _get_ingestion(youtube, broadcast):
    """Return (ingestion_address, stream_name, stream_id) for bound stream, or (None,None,None)."""
    try:
        stream_id = broadcast.get("contentDetails", {}).get("boundStreamId")
        if not stream_id:
            return None, None, None
        resp = youtube.liveStreams().list(part="id,cdn,status", id=stream_id).execute()
        items = resp.get("items", [])
        if not items:
            return None, None, None
        info = items[0]["cdn"].get("ingestionInfo", {})
        return info.get("ingestionAddress"), info.get("streamName"), stream_id
    except Exception as e:
        print(f"  [yt-api] Error getting stream ingestion info: {e}")
        return None, None, None


# ── Broadcast creation ────────────────────────────────────────────────────────

def _create_broadcast_and_stream(youtube, title, theme_name=None):
    """
    Create a new broadcast + ingestion stream and bind them.
    Returns (broadcast_id, stream_id, ingestion_address, stream_name, scheduled_start).
    Raises on failure.
    """
    now            = datetime.datetime.utcnow()
    # 1s in the future — YouTube requires scheduledStartTime to be in the future
    scheduled_start = (now + datetime.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    theme_label = theme_name.replace("_", " ").title() if theme_name else "lo-fi chill"
    description = (
        f"lo-fi hip hop radio 24/7 · {theme_label} · beats to study, work & relax\n\n"
        "No ads. No interruptions. Just continuous lo-fi frequencies generated fresh.\n\n"
        "🔔 Subscribe to catch new mixes and themed sessions\n"
        "👍 Like the stream if it helped you focus\n"
        "💬 Drop a comment — what are you working on right now?\n\n"
        "#lofi #lofihiphop #studymusic #chillhop #lofiradio"
    )

    # 1. Create broadcast
    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": scheduled_start,
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,
                "enableDvr": True,
                "latencyPreference": "ultraLow",
                "monitorStream": {"enableMonitorStream": False},
            },
        }
    ).execute()
    broadcast_id = broadcast["id"]
    print(f"  [yt-api] Broadcast created: {title[:60]}")
    print(f"  [yt-api] Watch URL: https://www.youtube.com/watch?v={broadcast_id}")

    # 2. Create ingestion stream
    stream = youtube.liveStreams().insert(
        part="snippet,cdn,status",
        body={
            "snippet": {"title": f"lofi-factory-{now.strftime('%Y%m%d-%H%M')}"},
            "cdn": {
                "ingestionType": "rtmp",
                "resolution": "720p",
                "frameRate": "variable",   # documented values: 30fps, 60fps, variable
            },
        }
    ).execute()
    stream_id   = stream["id"]
    ingestion   = stream["cdn"]["ingestionInfo"]
    ingest_addr = ingestion["ingestionAddress"]
    stream_name = ingestion["streamName"]

    # 3. Bind broadcast to stream
    youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()
    print("  [yt-api] Bound broadcast to ingestion stream")
    print(f"  [yt-api] RTMP: {ingest_addr}/***")

    return broadcast_id, stream_id, ingest_addr, stream_name, scheduled_start


# ── Main entry point ──────────────────────────────────────────────────────────

def setup_live_stream(theme_name=None, stream_key_override=None):
    """
    Full setup: auth → find or create broadcast → return RTMP URL + metadata.

    Returns a dict:
      rtmp_url        — full RTMP push URL (ingestion_address/stream_name)
      broadcast_id    — YouTube broadcast ID (None if API unavailable)
      stream_id       — YouTube stream/ingestion ID (None if API unavailable)
      scheduled_start — ISO8601 scheduled start time string
      youtube         — authenticated service object (None if API unavailable)

    Falls back to YT_STREAM_KEY env var if API is unavailable.
    """
    fallback_key = stream_key_override or os.environ.get("YT_STREAM_KEY", "")
    fallback_url = f"rtmp://a.rtmp.youtube.com/live2/{fallback_key}" if fallback_key else ""

    youtube = get_youtube_service()
    if youtube is None:
        if not fallback_key:
            print("  [yt-api] WARNING: No API credentials AND no YT_STREAM_KEY set!")
            print("           The stream cannot push to YouTube without one of these.")
        else:
            print("  [yt-api] Using env-var stream key (no API credentials)")
        return {
            "rtmp_url": fallback_url, "broadcast_id": None,
            "stream_id": None, "scheduled_start": None, "youtube": None,
        }

    # Try to reuse an existing ready/created broadcast (avoids quota usage)
    broadcast = _find_broadcast(youtube, "ready") or _find_broadcast(youtube, "created")
    if broadcast:
        bid   = broadcast["id"]
        btitle = broadcast["snippet"]["title"]
        bsched = broadcast["snippet"].get("scheduledStartTime")
        print(f"  [yt-api] Reusing broadcast: {btitle[:60]}")
        print(f"  [yt-api] Watch URL: https://www.youtube.com/watch?v={bid}")
        ingest_addr, stream_name, stream_id = _get_ingestion(youtube, broadcast)
        if ingest_addr and stream_name:
            return {
                "rtmp_url": f"{ingest_addr}/{stream_name}",
                "broadcast_id": bid, "stream_id": stream_id,
                "scheduled_start": bsched, "youtube": youtube,
            }
        print("  [yt-api] Existing broadcast has no bound stream — creating new one")

    # Create a fresh broadcast
    theme_label = theme_name.replace("_", " ").title() if theme_name else "Lo-Fi Chill"
    title = f"Lo-Fi Hip Hop Radio — {theme_label} | beats to relax/study to"[:100]
    try:
        broadcast_id, stream_id, ingest_addr, stream_name, scheduled_start = \
            _create_broadcast_and_stream(youtube, title, theme_name)
        return {
            "rtmp_url": f"{ingest_addr}/{stream_name}",
            "broadcast_id": broadcast_id, "stream_id": stream_id,
            "scheduled_start": scheduled_start, "youtube": youtube,
        }
    except Exception as e:
        print(f"  [yt-api] Broadcast creation failed: {e}")
        print("  [yt-api] Falling back to env-var stream key")
        return {
            "rtmp_url": fallback_url, "broadcast_id": None,
            "stream_id": None, "scheduled_start": None, "youtube": None,
        }


# ── Broadcast lifecycle ───────────────────────────────────────────────────────

def transition_to_live_async(youtube, broadcast_id, stream_id):
    """
    Background thread: poll stream health, then transition broadcast to LIVE.
    YouTube requires the encoder to be sending video before the transition is allowed.
    Call this right after ffmpeg starts.
    """
    def _run():
        deadline = time.time() + _TRANSITION_TIMEOUT
        print("  [yt-api] Waiting for stream to become active (up to 2 min)...")

        while time.time() < deadline:
            time.sleep(_POLL_INTERVAL)
            try:
                resp = youtube.liveStreams().list(
                    part="status", id=stream_id
                ).execute()
                items = resp.get("items", [])
                if items:
                    stream_status = items[0].get("status", {}).get("streamStatus", "")
                    health_status = items[0].get("status", {}).get("healthStatus", {}).get("status", "")
                    print(f"  [yt-api] Stream: {stream_status} / health: {health_status}")
                    if stream_status in ("active",):
                        break
            except Exception as e:
                print(f"  [yt-api] Status poll error: {e}")

        # Attempt transition to live (retry up to 3×)
        for attempt in range(3):
            try:
                youtube.liveBroadcasts().transition(
                    broadcastStatus="live",
                    id=broadcast_id,
                    part="id,status",
                ).execute()
                print("  [yt-api] *** BROADCAST IS LIVE — viewers can watch now ***")
                return
            except Exception as e:
                err = str(e)
                if "redundantTransition" in err or "alreadyLive" in err:
                    print("  [yt-api] Broadcast already live")
                    return
                print(f"  [yt-api] Transition attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    time.sleep(10)

        print("  [yt-api] Could not auto-transition — check YouTube Studio manually")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def end_broadcast(youtube, broadcast_id):
    """Transition broadcast to 'complete', ending the stream for viewers."""
    if not youtube or not broadcast_id:
        return
    print("  [yt-api] Ending broadcast...")
    try:
        youtube.liveBroadcasts().transition(
            broadcastStatus="complete",
            id=broadcast_id,
            part="id,status",
        ).execute()
        print("  [yt-api] Broadcast ended")
    except Exception as e:
        msg = str(e)
        if "invalidTransition" in msg or "redundantTransition" in msg:
            print("  [yt-api] Broadcast already ended")
        else:
            print(f"  [yt-api] Error ending broadcast: {e}")


# ── Live title updater ────────────────────────────────────────────────────────

class LiveTitleUpdater:
    """
    Background thread that updates the YouTube broadcast title as tracks change.
    Rate-limited to max 1 update per _TITLE_COOLDOWN seconds to conserve quota.
    """

    def __init__(self, youtube, broadcast_id, scheduled_start):
        self._yt      = youtube
        self._bid     = broadcast_id
        self._sched   = scheduled_start or \
                        datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        self._pending = None
        self._last    = 0.0
        self._lock    = threading.Lock()
        self._stop    = threading.Event()
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_track(self, title, genre):
        """Call when track changes. Queues a broadcast title update."""
        label = f"{title[:60]} | Lo-Fi Radio"
        with self._lock:
            self._pending = label

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            time.sleep(15)
            now = time.time()
            with self._lock:
                pending = self._pending
                if not (pending and now - self._last >= _TITLE_COOLDOWN):
                    pending = None

            if pending:
                try:
                    # update(part="snippet") replaces the whole snippet: any
                    # field left out (the description) is erased. Read the
                    # current snippet and change only the title.
                    resp = self._yt.liveBroadcasts().list(part="snippet", id=self._bid).execute()
                    items = resp.get("items") or []
                    if not items:
                        raise RuntimeError("broadcast not found")
                    current = items[0]["snippet"]
                    self._yt.liveBroadcasts().update(
                        part="snippet",
                        body={
                            "id": self._bid,
                            "snippet": {
                                "title": pending[:100],
                                "description": current.get("description", ""),
                                "scheduledStartTime": current.get("scheduledStartTime", self._sched),
                            },
                        }
                    ).execute()
                    # Only clear pending and advance cooldown on success (both under lock)
                    with self._lock:
                        if self._pending == pending:
                            self._pending = None
                        self._last = time.time()
                    print(f"\n  [yt-api] Stream title updated: {pending[:70]}")
                except Exception as e:
                    print(f"\n  [yt-api] Title update failed: {e} — will retry next cycle")
