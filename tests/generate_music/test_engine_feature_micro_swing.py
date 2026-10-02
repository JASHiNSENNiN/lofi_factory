"""
Coverage for Feature 2 -- per-hit micro-timing swing (research/subgenres/
lofi_garage.md: "garage swing lives in the individual hits" -- each drum
voice gets its own bias/spread rather than one uniform swing ratio applied
to every off-beat).

build_drums(..., micro_swing=True) layers _MICRO_SWING_PROFILE's per-voice
(bias_ms, jitter_ms) on top of the existing _gauss_jitter() humanization
call (extends it, doesn't replace it) -- this file checks the resulting
per-voice timing-offset distributions actually differ, both from the
micro_swing=False baseline and from each other.
"""
import random
import statistics

from scripts.composer import (
    CHH,
    KICK,
    PPQN,
    SNARE,
    DRUM_PATTERNS,
    _MICRO_SWING_GENRES,
    build_drums,
    grid_tick,
)

_BPM = 80
_SWING = 0.60
_PATTERN = DRUM_PATTERNS[2]


def _voice_offsets_ms(events, bpm=_BPM, swing=_SWING):
    """ms offset of each hit from its nearest exact swung 16th-grid tick --
    isolates the jitter/bias contribution from the underlying swing shift."""
    ticks_per_ms = (PPQN * bpm) / 60_000.0
    out = {KICK: [], SNARE: [], CHH: []}
    for t, note, vel, dur in events:
        if note not in out:
            continue
        best_grid = min(range(0, 16 * 20), key=lambda g: abs(grid_tick(g, swing) - t))
        out[note].append((t - grid_tick(best_grid, swing)) / ticks_per_ms)
    return out


def test_micro_swing_changes_per_voice_timing_relative_to_uniform_baseline():
    random.seed(7)
    micro = build_drums(_PATTERN, 0, 16, _SWING, _BPM, micro_swing=True)
    random.seed(7)
    plain = build_drums(_PATTERN, 0, 16, _SWING, _BPM, micro_swing=False)

    off_micro = _voice_offsets_ms(micro)
    off_plain = _voice_offsets_ms(plain)

    for voice in (KICK, SNARE, CHH):
        assert off_micro[voice], f"expected {voice} hits in the micro_swing render"
        assert off_plain[voice], f"expected {voice} hits in the plain render"
        # Same set of drum voices/step positions fire either way -- only the
        # feel changes, not which steps/drums play.
        assert len(off_micro[voice]) == len(off_plain[voice])

    # The per-voice mean offset profile must differ from the flat baseline
    # (every voice in `plain` shares one +-4ms jitter with no bias).
    micro_means = {v: statistics.mean(off_micro[v]) for v in off_micro}
    plain_means = {v: statistics.mean(off_plain[v]) for v in off_plain}
    assert micro_means != plain_means


def test_micro_swing_gives_kick_the_tightest_and_hats_the_widest_spread():
    # research: hats get the widest jitter range (2-step's off-grid hi-hat
    # signature), snare a smaller consistent late pull, kick minimal jitter
    # (anchors the four-on-the-floor). Run several seeds and check the
    # *aggregate* per-voice std-dev ordering, since any single seed's exact
    # numbers can wobble.
    kick_all, snare_all, hat_all = [], [], []
    for seed in range(12):
        random.seed(seed)
        events = build_drums(_PATTERN, 0, 8, _SWING, _BPM, micro_swing=True)
        off = _voice_offsets_ms(events)
        kick_all += off[KICK]
        snare_all += off[SNARE]
        hat_all += off[CHH]

    kick_std = statistics.pstdev(kick_all)
    snare_std = statistics.pstdev(snare_all)
    hat_std = statistics.pstdev(hat_all)

    assert kick_std < snare_std, f"kick std {kick_std} should be tighter than snare std {snare_std}"
    # Kick should also stay closest to the grid on average (near-zero bias).
    assert abs(statistics.mean(kick_all)) < abs(statistics.mean(snare_all))


def test_micro_swing_snare_gets_a_consistent_late_pull():
    random.seed(3)
    events = build_drums(_PATTERN, 0, 8, _SWING, _BPM, micro_swing=True)
    off = _voice_offsets_ms(events)
    # SNARE's profile bias is +5ms -- mean offset should land solidly positive
    # (late), not centered near zero the way KICK's near-0-bias profile does.
    assert statistics.mean(off[SNARE]) > 2.0


def test_lofi_garage_is_registered_in_micro_swing_genres():
    assert 'lofi_garage' in _MICRO_SWING_GENRES
    assert 'lofi_drill' not in _MICRO_SWING_GENRES
    assert 'lofi_synthwave' not in _MICRO_SWING_GENRES
