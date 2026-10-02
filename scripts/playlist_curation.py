"""
playlist_curation.py — data-driven pillar -> YouTube playlist assignment.

Replaces the previous static *duration*-keyed mapping in
scripts/upload_youtube.py (YT_PLAYLIST_STUDY / YT_PLAYLIST_SLEEP, chosen
purely by video length) with assignment by SEO **pillar** — the 5-pillar
taxonomy generate_seo.py already tags every concept with: temporal,
activity, emotional, aesthetic, cross_genre (see that module's docstring
and the "pillar" field on every concept dict it produces). Grouping by what
a video is *about* is a better fit for how viewers actually browse curated
playlists than grouping purely by how long it happens to run.

MIGRATION PATH (static .env table -> this module):
  1. In YouTube Studio, create (or reuse) one playlist per pillar you want
     to curate — you don't have to use all 5 right away.
  2. Set the matching env var(s) below to that playlist's ID, e.g.:
       YT_PLAYLIST_ACTIVITY=PLxxxxxxxxxxxxxxxx
  3. The old YT_PLAYLIST_STUDY / YT_PLAYLIST_SLEEP vars keep working as a
     duration-based FALLBACK for any pillar without its own playlist set
     (see resolve_playlist_id below), so migration can happen gradually,
     pillar by pillar, without ever leaving a video unfiled. Once every
     pillar you care about has its own ID, the old vars are dead weight and
     can be deleted from .env.

Playlist CREATION still requires an explicit human decision: youtube's API
can create a channel-visible playlist, but create_playlist_if_confirmed()
below only does so when the caller passes confirm=True (wired to publish.py's
`playlist create --confirm-create` flag / a webui confirmation dialog) —
never as a side effect of an unattended run.
"""
from __future__ import annotations

import os

# Mirrors generate_seo.py's 5-pillar taxonomy (see that module's docstring
# and every concept dict's "pillar" field). Duplicated here as plain data
# rather than imported: generate_seo.py doesn't export it as a public
# constant.
PILLARS = ["temporal", "activity", "emotional", "aesthetic", "cross_genre"]

# pillar -> env var holding that pillar's playlist ID. Data-driven so a 6th
# pillar later means adding one line here, not restructuring calling code.
PILLAR_ENV_VARS: dict[str, str] = {
    "temporal": "YT_PLAYLIST_TEMPORAL",
    "activity": "YT_PLAYLIST_ACTIVITY",
    "emotional": "YT_PLAYLIST_EMOTIONAL",
    "aesthetic": "YT_PLAYLIST_AESTHETIC",
    "cross_genre": "YT_PLAYLIST_CROSS_GENRE",
}

# The legacy duration-based table this module replaces (kept only as a
# fallback -- see resolve_playlist_id).
_LEGACY_LONG_DURATIONS = {"3 hours", "4 hours", "5 hours", "8 hours", "10 hours", "all night"}
YT_PLAYLIST_SLEEP = "YT_PLAYLIST_SLEEP"
YT_PLAYLIST_STUDY = "YT_PLAYLIST_STUDY"


def resolve_playlist_id(seo: dict, env: dict | None = None) -> str | None:
    """
    Pick a playlist ID for one upload's SEO dict. Priority:
      1. pillar-specific env var (YT_PLAYLIST_<PILLAR>), if the SEO dict's
         "pillar" is one of the known pillars and that var is set.
      2. legacy duration-based env var (YT_PLAYLIST_SLEEP / YT_PLAYLIST_STUDY),
         if still set -- so upgrading to this module doesn't silently stop
         playlist assignment for anyone who hasn't migrated .env yet.
      3. None (caller skips the playlist add, exactly as it always has when
         no matching env var is set).

    `env` defaults to os.environ; pass a plain dict in tests instead of
    mutating process environment.
    """
    env = os.environ if env is None else env
    pillar = str(seo.get("pillar") or "").strip().lower()
    var_name = PILLAR_ENV_VARS.get(pillar)
    if var_name:
        pid = (env.get(var_name) or "").strip()
        if pid:
            return pid

    duration = seo.get("duration", "")
    legacy_var = YT_PLAYLIST_SLEEP if duration in _LEGACY_LONG_DURATIONS else YT_PLAYLIST_STUDY
    pid = (env.get(legacy_var) or "").strip()
    return pid or None


def create_playlist_if_confirmed(youtube, title: str, *, description: str = "",
                                   privacy: str = "public", confirm: bool = False) -> dict | None:
    """
    Create a new channel playlist via the YouTube Data API -- but ONLY when
    confirm=True. Returns None (does nothing) otherwise.

    `confirm` must be threaded all the way from an explicit user action
    (publish.py's `playlist create <title> --confirm-create`, or a webui
    confirmation dialog) so nothing creates a real, channel-visible
    playlist as a side effect of an unattended run (e.g. lofi-auto.timer).
    """
    if not confirm:
        return None
    resp = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description, "defaultLanguage": "en"},
            "status": {"privacyStatus": privacy},
        },
    ).execute()
    return {"id": resp["id"], "title": resp["snippet"]["title"]}
