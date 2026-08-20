import random

from scripts.generate_music_gemini import (
    KEY_ROOTS,
    PROGRESSIONS,
    PROGRESSION_KEY,
    pick_params,
)

# Previously reachable via _pick_key_avoiding_recent's independent draw over
# every KEY_ROOTS entry, but never the real tonal center of any PROGRESSIONS
# entry -- picking one of these guaranteed a melody/chord key mismatch. See
# PROGRESSION_KEY's module comment.
_ORPHANED_KEYS = {'Em', 'F#m', 'Bm', 'Ebm', 'A', 'D'}


def test_progression_key_covers_every_progression():
    assert len(PROGRESSION_KEY) == len(PROGRESSIONS)


def test_progression_key_entries_are_valid_key_roots():
    for key in PROGRESSION_KEY:
        assert key in KEY_ROOTS


def test_pick_params_key_always_matches_its_progression():
    for i in range(200):
        random.seed(i)
        params = pick_params()
        assert params['key'] == PROGRESSION_KEY[params['progression']]


def test_pick_params_never_produces_an_orphaned_key():
    for i in range(200):
        random.seed(i)
        params = pick_params()
        assert params['key'] not in _ORPHANED_KEYS
