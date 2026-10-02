"""
Regression test for generate_tracks()'s track-order race: threads used to
be collected via concurrent.futures.as_completed() and *appended* to the
result list, so the returned order was whichever track finished first, not
the planned submission order (the "Track plan: X -> Y -> Z" the function
itself prints). Downstream code (run.py's SEO-alignment step) reads
paths[0]'s .meta.json assuming it's the first planned track -- under the
old code, a slow track 0 racing against a fast track 2 would silently make
paths[0] actually be track 2's file.
"""
import time

import scripts.composer as gmg


def test_generate_tracks_returns_submission_order_despite_completion_race(monkeypatch):
    # Track 2 finishes fastest, track 0 slowest -- completion order is
    # exactly reversed from submission order, so any completion-order bug
    # would be caught deterministically (no flakiness from timing luck).
    _DELAYS = {0: 0.06, 1: 0.03, 2: 0.0}

    def fake_generate_track(index=0, concept_hint=None, genre_hint=None,
                             song_dna=None, low_priority=False):
        time.sleep(_DELAYS.get(index, 0))
        return f"/fake/track_{index}.wav"

    monkeypatch.setattr(gmg, "generate_track", fake_generate_track)

    paths = gmg.generate_tracks(count=3, song_dna={"bpm": 70, "key": "C"})

    assert paths == ["/fake/track_0.wav", "/fake/track_1.wav", "/fake/track_2.wav"]


def test_generate_tracks_drops_failed_slot_keeps_order_of_rest(monkeypatch):
    def fake_generate_track(index=0, concept_hint=None, genre_hint=None,
                             song_dna=None, low_priority=False):
        if index == 1:
            raise RuntimeError("synthesis failed")
        return f"/fake/track_{index}.wav"

    monkeypatch.setattr(gmg, "generate_track", fake_generate_track)

    paths = gmg.generate_tracks(count=3, song_dna={"bpm": 70, "key": "C"})

    assert paths == ["/fake/track_0.wav", "/fake/track_2.wav"]


def test_generate_tracks_sequential_path_stays_in_order(monkeypatch):
    # workers = min(count, 3) -- count=1 takes the sequential (non-threaded)
    # branch, which already appended in order; confirm it's untouched.
    def fake_generate_track(index=0, concept_hint=None, genre_hint=None,
                             song_dna=None, low_priority=False):
        return f"/fake/track_{index}.wav"

    monkeypatch.setattr(gmg, "generate_track", fake_generate_track)

    paths = gmg.generate_tracks(count=1, song_dna={"bpm": 70, "key": "C"})

    assert paths == ["/fake/track_0.wav"]
