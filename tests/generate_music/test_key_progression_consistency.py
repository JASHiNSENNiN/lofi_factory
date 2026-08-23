import random

from scripts.generate_music_gemini import (
    KEY_ROOTS,
    PROGRESSIONS,
    PROGRESSION_KEY,
    pick_params,
)

# Previously (Phase 2a) reachable via _pick_key_avoiding_recent's independent
# draw over every KEY_ROOTS entry, but never the real tonal center of any
# PROGRESSIONS entry a subgenre could actually select -- picking one of these
# guaranteed a melody/chord key mismatch. See PROGRESSION_KEY's module
# comment. As of the "wire progressions 51-58 into subgenre configs" pass
# (config/genres/*.yaml progression_indices additions -- see e.g.
# hip_hop_lofi.yaml's #53, bedroom_pop.yaml's #51, lofi_jazz.yaml's #54/55/56)
# these keys are now genuinely reachable by design: several subgenres'
# research profiles gave a real harmonic justification for the new A/D/Em/
# F#m/Bm/Ebm progressions, so pick_params() can and should land on them now.
# Kept here as documentation of what "orphaned" used to mean, not as a
# still-true set.
_FORMERLY_ORPHANED_KEYS = {'Em', 'F#m', 'Bm', 'Ebm', 'A', 'D'}


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


def test_formerly_orphaned_keys_are_now_reachable():
    """Sanity-check that the Task-1 wiring actually did something: at least
    one of the previously-orphaned keys shows up over enough draws, now that
    config/genres/*.yaml subgenres reference progressions 51-58."""
    seen = set()
    for i in range(400):
        random.seed(i)
        params = pick_params()
        if params['key'] in _FORMERLY_ORPHANED_KEYS:
            seen.add(params['key'])
    assert seen, "expected at least one formerly-orphaned key to be reachable now"
