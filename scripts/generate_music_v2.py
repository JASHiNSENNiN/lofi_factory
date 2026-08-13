"""
generate_music_v2.py — Beta music generator (music-theory-correct algorithms).

Drop-in replacement for generate_music_gemini.py.
Activate with --music-v2 in run.py.

Improvements over v1:
  · Voice leading: full displacement minimizer across ALL voices (not just top note)
  · Melody: chord-tone weighted note pool + leading-tone approach boost
  · Motif: 8-variation pool with retrograde, invert, augment, fragment, transpose
  · Bass: per-4-bar-phrase rhythm templates (7 patterns, not identical every bar)
  · Humanization: Gaussian timing/velocity (clusters near grid, not flat random)
  · Melody: +10–25ms systematic behind-the-beat displacement (lo-fi pocket feel)
  · Drums: protect beat-1 kick and beat-2/4 snare; energy-scaled mutation rates
  · Hi-hat drag: per-instrument values (hats 20ms; kick stays tight at 3ms)
"""

import math, os, sys, json, time, random, tempfile
from collections import Counter
from dataclasses import dataclass, field
from itertools import product as _iproduct

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.generate_music_gemini import (  # noqa: E402
    PPQN, BAR, S16,
    KICK, SNARE, RIM, CHH, OHH, RIDE, CRASH,
    PROGRESSIONS, VOICING_OPTIONS, BASS_ROOTS, _GUIDE_TONES,
    DRUM_PATTERNS, DRUM_FILLS, _EUCL_HATS,
    KEY_ROOTS,
    get_pentatonic, get_dorian, get_phrygian, get_major,
    get_lydian, get_natural_minor, get_harmonic_minor, get_blues, get_whole_tone,
    grid_tick, abs_to_track, build_sustain_pedal,
    build_pad, build_intro_hats, build_break_hats,
    build_texture, build_counter_melody,
    _SUBGENRE_CONFIG, _SWING_RANGE, _SWING_DEFAULT, _COZY_SUBGENRES,
    _SUBGENRE_FX, _SUBGENRE_TEXTURE, _SUBGENRE_DRUM_KITS, _DEFAULT_DRUM_KIT_POOL,
    _SONG_FORMS, _FORM_BY_SUBGENRE, _SCALE_MODAL_LIFT,
    maybe_sub_chord, _tension, _apply_tension_to_drums, _chord_pcs_at_bar,
    pick_params, _build_diverse_params,
    _save_melody_pitch_classes, _append_recipe_log, _append_audio_quality_log,
    midi_to_wav, _pick_soundfont, MUSIC_DIR,
    GM_RHODES, GM_EP2, GM_VIBRAPHONE, GM_BASS, GM_STRINGS, GM_WARM_PAD,
)

# ── 1. Gaussian humanization ────────────────────────────────────────────────────

def _gauss_jitter(base_tick: int, ms: float, bpm: int, ppq: int = PPQN) -> int:
    """Gaussian timing jitter — clusters near grid, σ = ms/2, capped at ±1.5×ms."""
    ticks_per_ms = (ppq * bpm) / 60_000.0
    offset_ms = max(-ms * 1.5, min(ms * 1.5, random.gauss(0, ms * 0.5)))
    return max(0, base_tick + int(offset_ms * ticks_per_ms))


def _gauss_velocity(base_vel: int, sigma: float = 8.0) -> int:
    return max(1, min(127, round(random.gauss(base_vel, sigma))))


def _lofi_late(tick: int, bpm: int, ppq: int = PPQN) -> int:
    """Systematic late feel: melody lands +10–25ms behind the grid."""
    offset_ms = random.gauss(17, 4)
    ticks_per_ms = (ppq * bpm) / 60_000.0
    return max(0, tick + int(offset_ms * ticks_per_ms))


# ── 2. Voice leading v2 — full displacement minimizer ───────────────────────────

# Intervals (mod 12) treated as needing resolution — true "clash" dissonances
# (minor/major 2nd, tritone). Sevenths (10, 11) are deliberately excluded:
# this pipeline's VOICING_OPTIONS chords are jazz/lofi 7th- and 9th-chord
# voicings where a 7th is an idiomatic chord tone, not a species-counterpoint
# dissonance to be resolved away.
_DISSONANT_INTERVAL_CLASSES = {1, 2, 6}


def _voicing_transition_cost(prev_voicing: list[int], shifted_voicing: list[int]) -> float:
    """
    Species-counterpoint-inspired cost of moving from prev_voicing to
    shifted_voicing (shifted_voicing already has any octave shifts applied).
    Hand-rolled classical voice-leading rules (no neural net, no LLM), all
    scored PER VOICE PAIR independently (every pair of voices is checked on
    its own — not folded into one aggregate adjacent-pairs-only penalty):
      - total semitone displacement from prev_voicing
      - a parallel-fifths/octaves penalty for EVERY pair of voices (not just
        adjacent ones) moving in the same direction and landing on the same
        perfect 5th/octave interval class both before and after — the
        classic part-writing error, same rule Palestrina-style species
        counterpoint forbids between any two voices, not only neighbors
      - a small per-pair bonus for contrary motion between voices
      - a per-pair dissonance/suspension-resolution check: a dissonant
        interval (m2/M2/tritone) present between a voice pair in
        prev_voicing is rewarded if it resolves to a consonant interval by
        STEP (each voice moves <=2 semitones) in shifted_voicing — the
        standard "suspension resolves down/up by step" rule — and penalized
        if it is left hanging (still dissonant) or "resolved" by a leap
      - a spacing penalty for inner-voice gaps outside a natural
        close-position range (~3-12 semitones)
    Shared by _voice_lead_v2 (greedy, per-chord) and _voice_lead_progression_ga
    (whole-progression optimizer) so both apply identical rules — this
    function is a drop-in replacement, no restructuring needed on either
    caller's side.
    """
    n = min(len(shifted_voicing), len(prev_voicing))
    if n == 0:
        return 0.0
    displacement = sum(abs(shifted_voicing[i] - prev_voicing[i]) for i in range(n))
    moves = [shifted_voicing[i] - prev_voicing[i] for i in range(n)]

    parallel_penalty = 0.0
    contrary_bonus = 0.0
    dissonance_cost = 0.0

    for a in range(n):
        for b in range(a + 1, n):
            move_a, move_b = moves[a], moves[b]
            interval_prev = abs(prev_voicing[b] - prev_voicing[a]) % 12
            interval_now = abs(shifted_voicing[b] - shifted_voicing[a]) % 12

            # Parallel perfect 5th/octave: both voices move, in the same
            # direction, and the interval between them is a perfect 5th or
            # octave/unison both before and after the move.
            if move_a != 0 and move_b != 0:
                same_direction = (move_a > 0) == (move_b > 0)
                if same_direction and interval_prev in (0, 7) and interval_now in (0, 7):
                    parallel_penalty += 8.0

                # Contrary motion between this voice pair — mild bonus,
                # scored per pair (was a single outer-voice-only bonus).
                if not same_direction:
                    contrary_bonus += 1.0

            # Dissonance / suspension-resolution treatment: a dissonant
            # interval established in prev_voicing should resolve to a
            # consonance by stepwise motion; otherwise it's penalized
            # whether it's held unresolved or "resolved" by a leap.
            if interval_prev in _DISSONANT_INTERVAL_CLASSES:
                resolved_by_step = (
                    interval_now not in _DISSONANT_INTERVAL_CLASSES
                    and abs(move_a) <= 2 and abs(move_b) <= 2
                )
                dissonance_cost += -1.5 if resolved_by_step else 3.0

    spacing_penalty = 0.0
    for a in range(len(shifted_voicing) - 1):
        gap = shifted_voicing[a + 1] - shifted_voicing[a]
        if gap < 3:
            spacing_penalty += (3 - gap) * 1.5
        elif gap > 12:
            spacing_penalty += (gap - 12) * 1.0

    return displacement + parallel_penalty + spacing_penalty + dissonance_cost - contrary_bonus


def _voice_lead_v2(voicing_options: list[list[int]], prev_voicing: list[int]) -> list[int]:
    """
    Choose the voicing that minimizes _voicing_transition_cost, trying ±12
    semitone octave shifts on each voice independently (brute-force, exact —
    the search space per chord is tiny).
    """
    if not prev_voicing:
        return random.choice(voicing_options)

    def _cost(v: list[int]) -> float:
        n = min(len(v), len(prev_voicing))
        best = float('inf')
        for shifts in _iproduct([-12, 0, 12], repeat=n):
            shifted = [v[i] + shifts[i] for i in range(n)]
            if shifted != sorted(shifted):      # must stay ascending
                continue
            best = min(best, _voicing_transition_cost(prev_voicing, shifted))
        return best

    return min(voicing_options, key=_cost)


def _enumerate_shift_options(voicing: list[int]) -> list[list[int]]:
    """All valid (ascending-order-preserving) ±12-semitone octave-shift
    variants of a voicing — the same shift search _voice_lead_v2 does
    internally, but materialized as a list for the GA to choose from."""
    n = len(voicing)
    out = []
    for shifts in _iproduct([-12, 0, 12], repeat=n):
        shifted = [voicing[i] + shifts[i] for i in range(n)]
        if shifted == sorted(shifted):
            out.append(shifted)
    return out or [voicing]


def _build_voicing_gene_pools(chord_names: list[str]) -> list[list[list[int]]]:
    """
    Per-chord list of candidate voicings (every octave-shift variant of every
    curated VOICING_OPTIONS entry for that chord). Shared "search space"
    builder for both whole-progression optimizers (_voice_lead_progression_ga
    and _voice_lead_progression_annealing) so they explore identical gene
    pools and their resulting costs are directly comparable.
    """
    gene_pools: list[list[list[int]]] = []
    for chord_name in chord_names:
        options = VOICING_OPTIONS.get(chord_name, [[60, 64, 67]])
        variants: list[list[int]] = []
        for base in options:
            variants.extend(_enumerate_shift_options(base))
        gene_pools.append(variants or [options[0]])
    return gene_pools


def _chromosome_cost(gene_pools: list[list[list[int]]], chromosome: list[int]) -> float:
    """Total _voicing_transition_cost across an entire chromosome's chord sequence."""
    total = 0.0
    prev = None
    for i, gene_idx in enumerate(chromosome):
        voicing = gene_pools[i][gene_idx]
        if prev is not None:
            total += _voicing_transition_cost(prev, voicing)
        prev = voicing
    return total


def _voice_lead_progression_ga(progression: list[tuple[str, int]],
                                pop_size: int = 24, generations: int = 40) -> list[list[int]]:
    """
    Evolve voicing+octave-shift choices for an ENTIRE progression
    simultaneously (unlike _voice_lead_v2's greedy per-chord choice), via a
    genetic algorithm: tournament selection, single-point crossover,
    mutation, elitism. Solves the real limitation of greedy selection, which
    can get locally stuck (like greedy TSP) — global fitness considers every
    transition in the progression at once. Hand-rolled GA, no neural net, no
    LLM. Runs once per progression pick (~pop_size*generations*len(progression)
    cost evaluations — trivial cost, not a per-frame or per-render-loop cost).

    Returns one shifted voicing (list[int]) per chord in `progression`, in order.
    """
    chord_names = [c for c, _ in progression]
    gene_pools = _build_voicing_gene_pools(chord_names)

    def _random_chromosome() -> list[int]:
        return [random.randrange(len(pool)) for pool in gene_pools]

    def _fitness(chromosome: list[int]) -> float:
        return _chromosome_cost(gene_pools, chromosome)

    population = [_random_chromosome() for _ in range(pop_size)]
    best = min(population, key=_fitness)
    best_fit = _fitness(best)

    def _tournament(k: int = 3) -> list[int]:
        contenders = random.sample(population, min(k, len(population)))
        return min(contenders, key=_fitness)

    for _ in range(generations):
        next_gen = [best]   # elitism: never lose the best chromosome found so far
        while len(next_gen) < pop_size:
            parent_a, parent_b = _tournament(), _tournament()
            cut = random.randrange(1, len(chord_names)) if len(chord_names) > 1 else 0
            child = parent_a[:cut] + parent_b[cut:]
            if random.random() < 0.15:
                idx = random.randrange(len(child))
                child[idx] = random.randrange(len(gene_pools[idx]))
            next_gen.append(child)
        population = next_gen
        candidate = min(population, key=_fitness)
        candidate_fit = _fitness(candidate)
        if candidate_fit < best_fit:
            best, best_fit = candidate, candidate_fit

    return [gene_pools[i][gene_idx] for i, gene_idx in enumerate(best)]


def _voice_lead_progression_annealing(
    progression: list[tuple[str, int]],
    iterations: int = 600, start_temp: float = 12.0, cooling: float = 0.99,
    seed: int | None = None,
) -> list[list[int]]:
    """
    Simulated-annealing ALTERNATIVE to _voice_lead_progression_ga: same goal
    (minimize total _voicing_transition_cost across the whole chord
    sequence, same gene pools) and same cost function, but a different
    search strategy — a single temperature-scheduled random-restart local
    search instead of a population-based evolutionary search. Standard
    published algorithm (Kirkpatrick et al. 1983): start from a random
    voicing choice per chord, repeatedly propose a random neighbor move
    (re-pick one chord's voicing), accept it unconditionally if it improves
    total cost, or with probability exp(-delta/T) if it doesn't (escapes
    local minima), and geometrically cool T over the run so late iterations
    behave like plain hill-climbing.

    Returns one shifted voicing (list[int]) per chord in `progression`, in
    order — same return shape as _voice_lead_progression_ga, so callers can
    use either interchangeably (see _voice_lead_progression_best).
    """
    chord_names = [c for c, _ in progression]
    gene_pools = _build_voicing_gene_pools(chord_names)
    rng = random.Random(seed) if seed is not None else random

    current = [rng.randrange(len(pool)) for pool in gene_pools]
    current_cost = _chromosome_cost(gene_pools, current)
    best, best_cost = current[:], current_cost

    temp = start_temp
    for _ in range(iterations):
        movable = [i for i, pool in enumerate(gene_pools) if len(pool) > 1]
        if not movable:
            break
        idx = rng.choice(movable)
        neighbor = current[:]
        # Propose a different gene at this position (a real "move", not a
        # no-op self-transition).
        choices = [g for g in range(len(gene_pools[idx])) if g != current[idx]]
        neighbor[idx] = rng.choice(choices)
        neighbor_cost = _chromosome_cost(gene_pools, neighbor)

        delta = neighbor_cost - current_cost
        accept = delta <= 0 or rng.random() < math.exp(-delta / max(temp, 1e-6))
        if accept:
            current, current_cost = neighbor, neighbor_cost
            if current_cost < best_cost:
                best, best_cost = current[:], current_cost

        temp *= cooling

    return [gene_pools[i][gene_idx] for i, gene_idx in enumerate(best)]


def _voice_lead_progression_best(
    progression: list[tuple[str, int]],
    pop_size: int = 24, generations: int = 40, annealing_iterations: int = 600,
) -> tuple[list[list[int]], str]:
    """
    Run BOTH the genetic-algorithm optimizer and the simulated-annealing
    optimizer on the same progression and keep whichever finds the
    lower (better) total transition cost. Returns (voicings, winner) where
    winner is 'ga' or 'annealing', so callers can log which search strategy
    actually won for later analysis (see build_chords_v2's optimizer_log).
    Cheap either way — both are once-per-progression-pick searches, not
    per-frame or per-render-loop costs.
    """
    ga_voicings = _voice_lead_progression_ga(progression, pop_size=pop_size, generations=generations)
    sa_voicings = _voice_lead_progression_annealing(progression, iterations=annealing_iterations)

    def _total_cost(voicings: list[list[int]]) -> float:
        total = 0.0
        prev = None
        for v in voicings:
            if prev is not None:
                total += _voicing_transition_cost(prev, v)
            prev = v
        return total

    ga_cost = _total_cost(ga_voicings)
    sa_cost = _total_cost(sa_voicings)
    if sa_cost < ga_cost:
        return sa_voicings, 'annealing'
    return ga_voicings, 'ga'


def build_chords_v2(progression: list, start_bar: int, num_loops: int,
                    swing: float, bpm: int, ga_flag: list | None = None,
                    optimizer_log: list | None = None) -> list:
    """
    v1 build_chords with full-displacement voice leading and Gaussian humanization.
    ~15% of the time, uses a whole-progression-optimized voicing sequence
    (_voice_lead_progression_best — runs BOTH the genetic algorithm and the
    simulated-annealing optimizer and keeps whichever scores lower, see
    there) instead of the greedy per-chord _voice_lead_v2 — see there for why
    this can out-perform greedy selection. When active, secondary-dominant
    substitution (maybe_sub_chord) is skipped for that pass, since the
    optimizer already committed to voicings for the literal (unsubstituted)
    progression and substituting afterward would leave the chosen voicing
    not matching the actual chord being played.

    ga_flag: optional list — if the whole-progression optimizer fires, True
    is appended to it, so a caller building multiple sections (I/A/B) can
    cheaply check `bool(ga_flag)` afterward to know whether it was used
    anywhere in the track, for the recipe log. Name kept for backward
    compatibility with existing callers/tests; it now covers both search
    strategies, not just the GA.

    optimizer_log: optional list — the winning strategy ('ga' or
    'annealing') is appended to it each time the optimizer fires, so a
    caller can log which one actually won across the track for later
    analysis (see build_midi_v2's _append_recipe_log call).
    """
    events = []
    cursor = start_bar
    prev_voicing: list[int] = []

    ga_voicings: list[list[int]] | None = None
    if len(progression) >= 2 and random.random() < 0.15:
        try:
            ga_voicings, winner = _voice_lead_progression_best(progression)
            if ga_flag is not None:
                ga_flag.append(True)
            if optimizer_log is not None:
                optimizer_log.append(winner)
        except Exception:
            ga_voicings = None

    for _ in range(max(1, num_loops)):
        for chord_idx, (chord_name, dur_bars) in enumerate(progression):
            if ga_voicings is not None:
                voicing = ga_voicings[chord_idx]
            else:
                chord_name = maybe_sub_chord(chord_name, chord_idx)
                options  = VOICING_OPTIONS.get(chord_name, [[60, 64, 67]])
                voicing  = _voice_lead_v2(options, prev_voicing)
            prev_voicing = voicing

            base_t   = grid_tick(cursor * 16, swing)
            note_dur = int(dur_bars * BAR * 0.88)

            for i, note in enumerate(voicing):
                strum_t = int(i * random.uniform(5, 12) * (PPQN * bpm) / 60_000)
                t = _gauss_jitter(base_t, 14, bpm) + strum_t
                if i == len(voicing) - 1:  vel_val = _gauss_velocity(78, 10)
                elif i == 0:               vel_val = _gauss_velocity(58,  8)
                else:                      vel_val = _gauss_velocity(66, 10)
                events.append((t, note, vel_val, note_dur))

            if dur_bars >= 2 and random.random() < 0.5:
                b3_t = grid_tick(cursor * 16 + 8, swing)
                for note in voicing[-3:]:
                    events.append((_gauss_jitter(b3_t, 16, bpm), note,
                                   _gauss_velocity(50, 10), int(BAR * 0.45)))
            if dur_bars >= 2 and random.random() < 0.25:
                b2_t = grid_tick(cursor * 16 + 4, swing)
                for note in voicing[-2:]:
                    events.append((_gauss_jitter(b2_t, 16, bpm), note,
                                   _gauss_velocity(44, 8), int(BAR * 0.30)))
            cursor += dur_bars
    return events


# ── 3. Motif v2 — dataclass with 8 transformations ──────────────────────────────

@dataclass
class Motif:
    pitches:    list[int]
    durations:  list[float] = field(default_factory=list)   # relative (unused in melody timing)
    velocities: list[int]   = field(default_factory=list)

    def retrograde(self) -> 'Motif':
        return Motif(self.pitches[::-1], self.durations[::-1] if self.durations else [],
                     self.velocities[::-1] if self.velocities else [])

    def invert(self, axis: int) -> 'Motif':
        return Motif([2 * axis - p for p in self.pitches],
                     self.durations[:], self.velocities[:])

    def transpose(self, st: int) -> 'Motif':
        return Motif([p + st for p in self.pitches],
                     self.durations[:], self.velocities[:])

    def augment(self, f: float = 2.0) -> 'Motif':
        return Motif(self.pitches[:], [d * f for d in self.durations],
                     self.velocities[:])

    def diminish(self, f: float = 0.5) -> 'Motif':
        return self.augment(f)

    def fragment(self, n: int = 2) -> 'Motif':
        return Motif(self.pitches[:n], self.durations[:n], self.velocities[:n])


# ── 3b. L-system motif/phrase generator ──────────────────────────────────────
# Lindenmayer-system generative grammar (Prusinkiewicz & Lindenmayer, "The
# Algorithmic Beauty of Plants") applied to melody instead of plant geometry:
# an axiom string is iteratively expanded via per-symbol production rules,
# then the resulting symbol string is interpreted as a sequence of melodic
# operations on a scale-degree cursor. An ADDITIONAL phrase-generation
# source alongside the classical transforms above (retrograde/invert/
# transpose/augment/fragment) — wired into _apply_motif_variation's
# variation pool as one more selectable entry, not a replacement for any of
# the existing ones. Deterministic given a seed, matching the rest of the
# pipeline's reproducibility conventions.

# Melodic alphabet:
#   U - step up one scale degree      D - step down one scale degree
#   S - repeat (sustain) current note T - transpose (toggle +1 octave)
#   [ - push (save) cursor state      ] - pop (restore) cursor state —
#       classic Lindenmayer bracketed-branching notation, giving the
#       melody a "return to a home note" character instead of a pure
#       one-way random walk.
_LSYSTEM_PRESETS: list[tuple[str, dict[str, str]]] = [
    ('U', {'U': 'UDU', 'D': 'DUD'}),            # symmetric zigzag fractal
    ('U', {'U': 'U[D]U', 'D': 'D[U]D'}),        # branching zigzag, returns to branch point
    ('US', {'U': 'US', 'D': 'DS', 'S': 'US'}),  # terraced ascending steps with sustains
    ('U', {'U': 'UUD', 'D': 'DDU'}),            # asymmetric climb
    ('T', {'T': 'UTD', 'U': 'U', 'D': 'D'}),    # octave-anchored motif
]


def _lsystem_expand(axiom: str, rules: dict[str, str], iterations: int, max_len: int = 64) -> str:
    """
    Iteratively expand an L-system axiom via per-symbol production rules.
    Bounded: stops expanding (keeping the last valid generation) once the
    NEXT expansion would exceed `max_len`, so output length stays musically
    bounded rather than growing exponentially the way raw L-system expansion
    normally does (that unbounded growth is the point for plant geometry,
    but a melodic phrase needs a sane, bounded length).
    """
    s = axiom
    for _ in range(max(0, iterations)):
        nxt = ''.join(rules.get(ch, ch) for ch in s)
        if len(nxt) > max_len:
            break
        s = nxt
    return s


def _lsystem_to_pitches(symbols: str, scale_notes: list[int], start_idx: int) -> list[int]:
    """Interpret an L-system symbol string as melodic operations on a
    scale-degree cursor (see the alphabet comment above). Non-melodic
    symbols other than U/D/S/T/[/] are ignored. Emits one pitch per U/D/S/T
    symbol encountered (push/pop only affect state, they emit nothing)."""
    n = len(scale_notes)
    if n == 0:
        return []
    idx = max(0, min(n - 1, start_idx))
    octave_offset = 0
    stack: list[tuple[int, int]] = []
    pitches: list[int] = []
    for ch in symbols:
        if ch == 'U':
            idx = min(n - 1, idx + 1)
            pitches.append(scale_notes[idx] + octave_offset)
        elif ch == 'D':
            idx = max(0, idx - 1)
            pitches.append(scale_notes[idx] + octave_offset)
        elif ch == 'S':
            pitches.append(scale_notes[idx] + octave_offset)
        elif ch == 'T':
            octave_offset = 12 if octave_offset == 0 else 0   # toggle; avoids runaway octave drift
            pitches.append(scale_notes[idx] + octave_offset)
        elif ch == '[':
            stack.append((idx, octave_offset))
        elif ch == ']':
            if stack:
                idx, octave_offset = stack.pop()
    return pitches


def generate_lsystem_motif(scale_notes: list[int], length: int = 8,
                            seed: int | None = None) -> Motif:
    """
    Generate a melodic Motif via L-system string expansion (see module
    comment above). Picks one of a small pool of axiom+production-rule
    presets, expands it a bounded number of iterations, then walks the
    resulting symbol string as scale-degree operations. Deterministic given
    `seed` (uses a local Random instance so it never disturbs the pipeline's
    global random stream when called with an explicit seed).
    """
    if not scale_notes:
        return Motif([60])
    rng = random.Random(seed) if seed is not None else random
    axiom, rules = rng.choice(_LSYSTEM_PRESETS)
    iterations = rng.choice([2, 3, 3, 4])
    symbols = _lsystem_expand(axiom, rules, iterations, max_len=max(8, length * 4))
    start_idx = rng.randrange(len(scale_notes))
    pitches = _lsystem_to_pitches(symbols, scale_notes, start_idx)
    if not pitches:
        pitches = [scale_notes[start_idx]]
    length = max(1, length)
    return Motif(pitches[:length])


def _generate_motif_v2(scale_notes: list[int], length: int = 4) -> Motif:
    """Generate a seed motif using stepwise motion."""
    if not scale_notes:
        return Motif([60])
    start = random.randint(len(scale_notes) // 4,
                           max(len(scale_notes) // 4, 3 * len(scale_notes) // 4))
    pitches = [scale_notes[start]]
    for _ in range(length - 1):
        idx  = scale_notes.index(pitches[-1])
        step = random.choice([-2, -1, -1, 0, 1, 1, 2])
        pitches.append(scale_notes[max(0, min(len(scale_notes) - 1, idx + step))])
    return Motif(pitches)


def _apply_motif_variation(motif: Motif, scale_notes: list[int], var_idx: int,
                            section: str = 'A') -> list[int]:
    """Apply one of 9 variations; return list of pitches clamped to scale range."""
    root = scale_notes[len(scale_notes) // 2]
    lo, hi = scale_notes[0], scale_notes[-1]

    variations = [
        lambda m: m.retrograde(),
        lambda m: m.invert(axis=root),
        lambda m: m.transpose(2),
        lambda m: m.transpose(-2),
        lambda m: m.fragment(max(2, len(m.pitches) // 2)),
        lambda m: m.fragment(max(2, len(m.pitches) // 2)).retrograde(),
        lambda m: m,                        # literal repeat
        lambda m: m.transpose(4 if random.random() < 0.5 else -4),
        # L-system-generated phrase (see generate_lsystem_motif) — an
        # additional GENERATIVE source alongside the classical transforms
        # above, rather than a transform of `m` itself. Unseeded here (uses
        # the pipeline's global random stream) so it stays governed by
        # whatever top-level seed the caller set, same as every other
        # variation in this pool.
        lambda m: generate_lsystem_motif(scale_notes, length=max(3, len(m.pitches))),
    ]
    # B section: prefer slower feel — augment is conceptual (we stretch spacing externally)
    if section == 'B':
        variations[4] = lambda m: m.invert(axis=root).fragment(max(2, len(m.pitches) // 2))

    try:
        result = variations[var_idx % len(variations)](motif).pitches
    except Exception:
        result = motif.pitches[:]
    return [max(lo, min(hi, p)) for p in result]


# ── 4. Melody v2 — chord-tone weighted note pool ────────────────────────────────

MELODY_WEIGHTS = {
    'chord_tone': 4.0,
    'approach':   1.8,   # semitone below a chord tone
    'scale_pass': 2.0,
    'chromatic':  0.3,
}


def _build_note_pool(
    scale_notes: list[int],
    chord_pcs: set[int],
    prev_note: int | None,
    markov_nodes: dict | None = None,
) -> tuple[list[int], list[float]]:
    """
    Return (candidates, weights) for next melody note. markov_nodes (optional,
    isobar.MarkovLearner-style pitch-class transition table) additively boosts
    candidates matching what the source melody's own statistics favor after
    prev_note — blended into, not a replacement for, the chord-tone weighting.
    """
    candidates: list[int] = []
    weights: list[float]  = []

    markov_boost_pcs: set[int] = set()
    if markov_nodes and prev_note is not None:
        node = markov_nodes.get(prev_note % 12, markov_nodes.get(str(prev_note % 12)))
        if node:
            keys = node.keys() if isinstance(node, dict) else node
            markov_boost_pcs = {int(k) % 12 for k in keys}

    for n in scale_notes:
        if prev_note is not None and abs(n - prev_note) > 12:
            continue                         # skip octave+ leaps

        pc = n % 12
        if pc in chord_pcs:
            w = MELODY_WEIGHTS['chord_tone']
        elif (pc + 1) % 12 in chord_pcs:    # semitone below a chord tone = approach
            w = MELODY_WEIGHTS['approach']
        else:
            w = MELODY_WEIGHTS['scale_pass']

        if prev_note is not None and abs(n - prev_note) > 5:
            w *= 0.5                         # penalize large leaps

        if pc in markov_boost_pcs:
            w *= 1.8                         # Markov nudge (additive, not exclusive)

        candidates.append(n)
        weights.append(max(w, 0.01))

    return candidates, weights


def _pick_melody_note(scale_notes: list[int], chord_pcs: set[int],
                      prev_note: int | None, markov_nodes: dict | None = None) -> int:
    cands, wts = _build_note_pool(scale_notes, chord_pcs, prev_note, markov_nodes)
    if not cands:
        return random.choice(scale_notes)
    return random.choices(cands, weights=wts)[0]


def _get_scale_notes(key_root: int, scale: str) -> list[int]:
    builders = {
        'dorian':        get_dorian,
        'phryg':         get_phrygian,
        'major':         get_major,
        'lydian':        get_lydian,
        'natural_minor': get_natural_minor,
        'harmonic_minor':get_harmonic_minor,
        'blues':         get_blues,
        'whole_tone':    get_whole_tone,
        'major_pent':    lambda r: [n for o in range(3)
                                    for i in [0, 2, 4, 7, 9]
                                    for n in [r + i + o * 12]
                                    if 53 <= r + i + o * 12 <= 86],
        'mixo':          lambda r: [n for o in range(3)
                                    for i in [0, 2, 4, 5, 7, 9, 10]
                                    for n in [r + i + o * 12]
                                    if 53 <= r + i + o * 12 <= 86],
    }
    builder = builders.get(scale, get_pentatonic)
    return sorted(set(builder(key_root)))


def build_melody_v2(
    key_root: int, start_bar: int, num_bars: int,
    swing: float, bpm: int,
    density: str = 'sparse',
    scale: str = 'pent',
    motif: Motif | None = None,
    progression: list | None = None,
    prog_bars: int | None = None,
    section: str = 'A',
    markov_nodes: dict | None = None,
) -> list:
    """
    Motif-based melody using chord-tone weighted note selection.
    Applies behind-the-beat displacement for lo-fi pocket feel.
    markov_nodes: optional pitch-class transition table blended into note
    selection via _pick_melody_note/_build_note_pool (see there).
    """
    notes_scale = _get_scale_notes(key_root, scale)
    if not notes_scale:
        return []

    if motif is None:
        motif = _generate_motif_v2(notes_scale, length=random.randint(3, 5))

    var_idx   = 0
    events    = []
    bar       = start_bar
    rest_min  = 2 if density == 'sparse' else 1

    while bar < start_bar + num_bars:
        if random.random() < 0.72:
            phrase_pitches = _apply_motif_variation(motif, notes_scale, var_idx, section)
            var_idx += 1
            phrase_len   = len(phrase_pitches)
            phrase_start = bar * 16 + random.randint(0, 5)

            prev_note: int | None = None
            for i, note in enumerate(phrase_pitches):
                g = phrase_start + i * random.randint(2, 5)
                if g >= (start_bar + num_bars) * 16:
                    break

                # Chord-aware note selection
                chord_pcs: set[int] = set()
                if progression and prog_bars:
                    chord_pcs = _chord_pcs_at_bar(progression, bar, prog_bars)

                note = _pick_melody_note(notes_scale, chord_pcs, prev_note, markov_nodes)

                # Phi-point contour: ascending before 0.618, descending after
                pos = i / max(1, phrase_len - 1)
                if pos < 0.618:
                    step = random.choice([-1, 0, 1, 1, 2])
                else:
                    step = random.choice([-2, -2, -1, -1, 0])
                idx  = notes_scale.index(note) if note in notes_scale else len(notes_scale) // 2
                idx  = max(0, min(len(notes_scale) - 1, idx + step))
                note = notes_scale[idx]
                prev_note = note

                # Velocity arc: louder near phi-point climax
                climax_dist = abs(pos - 0.618)
                vel_arc     = int(12 * (1.0 - climax_dist))
                beat_pos    = g % 16
                vel_bonus   = 8 if beat_pos == 0 else (4 if beat_pos == 8 else 0)

                base_t = grid_tick(g, swing)
                t      = _gauss_jitter(base_t, 22, bpm)
                t      = _lofi_late(t, bpm)            # systematic late feel

                # Grace note: acciaccatura on first note of phrase (15%)
                if i == 0 and random.random() < 0.15 and len(notes_scale) > 2:
                    n_idx   = notes_scale.index(note) if note in notes_scale else len(notes_scale) // 2
                    gn_note = notes_scale[max(0, n_idx - 1)]
                    grace_t = max(0, t - int(S16 * 0.35))
                    events.append((grace_t, gn_note, _gauss_velocity(38, 6), int(S16 * 0.30)))

                dur = int(BAR * random.uniform(0.22, 0.72))
                if random.random() < 0.30:
                    dur = int(dur * 1.5)
                events.append((t, note, _gauss_velocity(70 + vel_bonus + vel_arc, 13), dur))

            bar += phrase_len + random.randint(rest_min, rest_min + 3)
        else:
            bar += random.randint(2, 5)

    return events


# ── 5. Bass v2 — per-phrase rhythm templates ────────────────────────────────────

# (16th-note step offsets from bar start, guide_tone_type)
# guide_tone_type: 'root', 'fifth', 'guide' (3rd or 7th when walking)
BASS_RHYTHMS = [
    ([0, 6, 8, 14], 'guide'),       # beat 1, 2+, 3, 4+ — classic lofi
    ([0, 4, 8, 12], 'root'),        # straight quarters
    ([0, 6, 8],     'guide'),       # sparse (no beat 4)
    ([0, 3, 8, 11], 'fifth'),       # syncopated off-beat emphasis
    ([0, 8],        'root'),        # ultra-minimal (beats 1 and 3 only)
    ([0, 5, 8, 13], 'guide'),       # late 2, late 4 (behind the beat)
    ([0, 6, 10, 14],'fifth'),       # beats 1, 2+, 3+, 4+ — walking feel
]


def _bass_phrase_rhythm(walking: bool) -> tuple:
    if walking:
        pool = [r for r in BASS_RHYTHMS if len(r[0]) >= 3]
    else:
        pool = BASS_RHYTHMS
    return random.choice(pool)


def build_bass_v2(
    progression: list, start_bar: int, num_loops: int,
    swing: float, bpm: int, walking: bool = False,
) -> list:
    """
    Bass with per-4-bar-phrase rhythm template + chromatic approach on chord changes.
    """
    events = []
    cursor = start_bar
    phrase_rhythm: tuple | None = None
    phrase_bar_count = 0

    for _ in range(max(1, num_loops)):
        prog_bars = sum(d for _, d in progression)
        for chord_idx, (chord_name, dur_bars) in enumerate(progression):
            root          = BASS_ROOTS.get(chord_name, 45)
            next_chord    = progression[(chord_idx + 1) % len(progression)][0]
            next_root     = BASS_ROOTS.get(next_chord, root)
            approach_note = next_root - 1
            if abs(approach_note - root) > 5:
                approach_note = root + 2

            third_off, seventh_off = _GUIDE_TONES.get(chord_name, (3, 10))
            fifth_note  = root + 7
            guide_note  = root + (third_off if walking else 7)
            beat3_note  = root + (seventh_off if walking else 0)

            for bar in range(dur_bars):
                abs_bar = cursor + bar

                # Pick a new template at the start of each 4-bar phrase
                if phrase_bar_count % 4 == 0 or phrase_rhythm is None:
                    phrase_rhythm = _bass_phrase_rhythm(walking)
                phrase_bar_count += 1

                steps, gt_type = phrase_rhythm
                is_last_bar_in_chord = (bar == dur_bars - 1)

                # Walking bass fill in last bar of progression (walking=True, 40%)
                if walking and is_last_bar_in_chord and chord_idx == len(progression) - 1 \
                        and random.random() < 0.40:
                    walk_notes = ([root + 7, root + 5, root + 2, root]
                                  if random.random() < 0.6
                                  else [root, root + 2, root + 4, root + 7])
                    for beat, note in enumerate(walk_notes):
                        t = _gauss_jitter(grid_tick(abs_bar * 16 + beat * 4, swing), 8, bpm)
                        events.append((t, note, _gauss_velocity(72, 10), int(PPQN * 0.85)))
                    continue

                # Template-driven bass notes
                for step in steps:
                    if step == 14 and is_last_bar_in_chord:
                        # Approach note on beat 4-and before chord change
                        if random.random() < 0.60:
                            t = _gauss_jitter(grid_tick(abs_bar * 16 + 14, swing), 8, bpm)
                            events.append((t, approach_note, _gauss_velocity(60, 10), int(S16 * 1.5)))
                        continue

                    if step == 0:
                        note = root
                        vel  = _gauss_velocity(80, 10)
                        dur  = int(BAR * 0.82)
                    elif gt_type == 'fifth':
                        note = fifth_note
                        vel  = _gauss_velocity(68, 12)
                        dur  = int(BAR * 0.35)
                    elif gt_type == 'guide' and step >= 6:
                        note = guide_note if step < 10 else beat3_note
                        vel  = _gauss_velocity(68, 12)
                        dur  = int(BAR * 0.40)
                    else:
                        note = root
                        vel  = _gauss_velocity(72, 10)
                        dur  = int(BAR * 0.35)

                    t = _gauss_jitter(grid_tick(abs_bar * 16 + step, swing), 8, bpm)
                    events.append((t, note, vel, dur))

            cursor += dur_bars
    return events


# ── 6. Drums v2 — protected steps + energy-scaled mutation ──────────────────────

# Steps (0-15) that must NOT be dropped regardless of mutation
PROTECTED_STEPS: dict[str, set[int]] = {
    'kick':  {0},          # beat 1 always
    'snare': {4, 12},      # beats 2 and 4 always
    'rim':   set(),
    'hat':   set(),
    'ride':  set(),
}

# Per-instrument off-beat drag (ms) — kick stays tight; hats drag
HAT_DRAG_MS: dict[str, float] = {
    'kick':       3.0,
    'snare':      5.0,
    'hat_closed': 20.0,
    'hat_open':   25.0,
    'ride':       12.0,
}

_DRUM_NOTE_TYPE: dict[int, str] = {
    KICK:  'kick',
    SNARE: 'snare',
    RIM:   'rim',
    CHH:   'hat',
    OHH:   'hat',
    RIDE:  'ride',
}


def _mutate_drum_step(drum_note: int, step: int, vel: int, energy: float) -> int:
    """Return (possibly mutated) velocity. 0 = drop the hit."""
    inst = _DRUM_NOTE_TYPE.get(drum_note, 'hat')
    if step in PROTECTED_STEPS.get(inst, set()):
        return vel

    drop_p  = 0.06 * (1.0 - energy * 0.5)
    ghost_p = 0.05 * energy

    r = random.random()
    if r < drop_p:
        return 0
    elif r < drop_p + ghost_p:
        return random.randint(28, 42)
    return vel


def build_drums_v2(
    pattern: dict, start_bar: int, num_bars: int,
    swing: float, bpm: int,
    fill_bars: set | None = None,
    energy: float = 0.7,
) -> list:
    """
    v2 drum builder: protected structural hits, Gaussian timing,
    per-instrument hat drag, energy-scaled mutation.
    """
    events     = []
    fill_bars  = fill_bars or set()
    fill_tmpl  = random.choice(DRUM_FILLS)
    eucl_hat   = random.choice(list(_EUCL_HATS.values())) if random.random() < 0.15 else None
    eucl_layer2 = random.choice(list(_EUCL_HATS.values())) if random.random() < 0.10 else None
    eucl_layer2_note = random.choice([OHH, RIM]) if eucl_layer2 is not None else None

    for bar in range(num_bars):
        abs_bar  = start_bar + bar
        use_fill = abs_bar in fill_bars
        hat_run  = (bar % 4 == 3)

        for step in range(16):
            src = fill_tmpl if use_fill else pattern

            for drum_note, vels in src.items():
                inst = _DRUM_NOTE_TYPE.get(drum_note, 'hat')

                # Per-instrument swing: hats slightly tighter than kick/snare
                elem_swing = swing * (0.92 if drum_note in (CHH, RIDE) else 1.0)
                base_t = grid_tick(abs_bar * 16 + step, elem_swing)

                # Per-instrument off-beat drag (replaces flat uniform drag)
                if step % 4 == 2:
                    drag_ms = HAT_DRAG_MS.get(
                        'hat_closed' if drum_note == CHH else
                        'hat_open'   if drum_note == OHH else
                        inst,
                        0.0
                    )
                    if drag_ms > 0:
                        drag_ticks = int(random.gauss(drag_ms, drag_ms * 0.2)
                                         * (PPQN * bpm) / 60_000.0)
                        base_t += max(0, drag_ticks)

                vel_val = vels[step % 16]

                # Euclidean CHH override
                if eucl_hat is not None and drum_note == CHH and not use_fill:
                    vel_val = 55 if eucl_hat[step % len(eucl_hat)] else 0

                # Independent second Euclidean layer (OHH or RIM)
                if (eucl_layer2 is not None and drum_note == eucl_layer2_note
                        and not use_fill):
                    vel_val = 45 if eucl_layer2[step % len(eucl_layer2)] else 0

                # Energy-aware mutation (respects protected steps)
                if not use_fill:
                    vel_val = _mutate_drum_step(drum_note, step, vel_val, energy)

                # Hi-hat run on last beat every 4 bars
                if hat_run and drum_note == CHH and step >= 12:
                    vel_val = max(vel_val, _gauss_velocity(55, 10))

                if vel_val > 0:
                    t = _gauss_jitter(base_t, 4, bpm)
                    events.append((t, drum_note, _gauss_velocity(vel_val, 8), 25))

    return events


# ── 7. MIDI builder v2 ──────────────────────────────────────────────────────────

_BASS_PROG_V2 = {
    'lofi_jazz': 35, 'bossa_lofi': 35, 'jazz_cafe': 35, 'piano_lofi': 35,
    'hip_hop_lofi': 38, 'lofi_phonk': 38, 'lofi_house': 38, 'vaporwave': 38,
    'lo_fi_funk': 36, 'neo_soul': 36,
}


def build_midi_v2(params: dict, output_path: str) -> str:
    import mido

    bpm       = int(params['bpm'])
    prog_idx  = int(params['progression']) % len(PROGRESSIONS)
    key       = params.get('key', 'Am')
    swing     = float(params.get('swing', 0.58))
    mood      = params.get('mood', '')
    density   = params.get('melody_density', 'sparse')
    scale     = params.get('melody_scale', 'pent')
    walking   = bool(params.get('bass_walking', False))
    energy    = params.get('drum_energy', 'medium')
    sub_genre = params.get('sub_genre', 'chillhop')
    markov_nodes = params.get('markov_melody_nodes')

    # A procedurally-generated progression (Markov walk, ~18% of the time —
    # see generate_music_gemini.generate_progression) takes priority over the
    # curated table. The music21-backed functional-harmony engine (see
    # harmony_engine.py, wired into pick_params/_build_diverse_params, both
    # shared with v1) takes top priority when present — see the matching
    # comment in generate_music_gemini.build_midi().
    prog      = (params.get('harmony_progression') or params.get('generated_progression')
                 or PROGRESSIONS[prog_idx])
    prog_bars = sum(d for _, d in prog)
    key_root  = KEY_ROOTS.get(key, 57)

    pat_a_idx = int(params.get('drum_pattern_a', random.randint(0, len(DRUM_PATTERNS) - 1)))
    pat_b_idx = int(params.get('drum_pattern_b', random.randint(0, len(DRUM_PATTERNS) - 1)))
    pat_a     = params.get('drum_pattern_a_generated') or DRUM_PATTERNS[pat_a_idx % len(DRUM_PATTERNS)]
    pat_b     = params.get('drum_pattern_b_generated') or DRUM_PATTERNS[pat_b_idx % len(DRUM_PATTERNS)]

    _cfg          = _SUBGENRE_CONFIG.get(sub_genre, {})
    piano_prog    = _cfg.get('piano', GM_RHODES)
    mel_prog      = _cfg.get('melody', 0)
    forced_energy = _cfg.get('energy')
    if forced_energy:
        energy = forced_energy
    energy_mult   = {'low': 0.78, 'medium': 1.0, 'high': 1.20}.get(energy, 1.0)
    energy_float  = {'low': 0.4,  'medium': 0.7,  'high': 1.0 }.get(energy, 0.7)

    form_name = _FORM_BY_SUBGENRE.get(sub_genre, 'standard')
    form      = _SONG_FORMS[form_name]
    TOTAL     = sum(prog_bars * n for _, n in form)
    fill_bars: set[int] = set()
    c = 0
    for _sec, _n in form:
        c += prog_bars * _n
        fill_bars.add(c - 1)

    # Shared motif scale (motif itself recomputed fresh per retry below)
    motif_scale  = _get_scale_notes(key_root, scale)

    print(f"  [v2] BPM={bpm} key={key} prog={prog_idx} swing={int(swing*100)}% "
          f"energy={energy} sub={sub_genre} walk={walking} form={form_name} mood='{mood}' | {TOTAL} bars")

    # ── Build events, with a quality-gate retry loop (see build_midi() in
    # generate_music_gemini.py for the identical pattern / rationale) ──────
    try:
        from scripts.track_quality import score_track_quality, MIN_QUALITY_SCORE, MAX_RETRIES
    except Exception:
        score_track_quality, MIN_QUALITY_SCORE, MAX_RETRIES = None, 0.0, 0

    best_events = None
    best_score = -1.0
    best_failures: list = []
    attempts_used = 0
    ga_flag: list = []
    optimizer_log: list = []

    for attempt in range(1 + MAX_RETRIES):
        attempts_used = attempt + 1

        break_scale    = scale
        break_key_root = key_root
        if random.random() < 0.35 and scale in _SCALE_MODAL_LIFT:
            break_scale    = _SCALE_MODAL_LIFT[scale]
            break_key_root = key_root + 3
        track_motif = _generate_motif_v2(motif_scale, random.randint(3, 5)) if motif_scale else None

        piano_ev    = []
        bass_ev     = []
        drum_ev     = []
        mel_ev      = []
        pad_ev      = []
        cmelo_ev    = []
        texture_ev  = []
        sustain_ev  = []
        active_bars = 0

        cursor = 0
        for sec_label, n_loops in form:
            sec_start = cursor
            sec_bars  = prog_bars * n_loops

            if sec_label == 'I':
                piano_ev   += build_chords_v2(prog, sec_start, n_loops, swing, bpm, ga_flag, optimizer_log)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
                bass_s = sec_start + min(2, prog_bars - 1)
                bass_ev += build_bass_v2(prog, bass_s, 1, swing, bpm, False)
                hat_s = sec_start + min(2, prog_bars - 1)
                hat_b = sec_bars - (hat_s - sec_start)
                if hat_b > 0:
                    drum_ev += build_intro_hats(hat_s, hat_b, swing, bpm)
                cmelo_ev += build_counter_melody(key_root, sec_start, sec_bars, swing, bpm)

            elif sec_label == 'A':
                piano_ev   += build_chords_v2(prog, sec_start, n_loops, swing, bpm, ga_flag, optimizer_log)
                bass_ev    += build_bass_v2(prog, sec_start, n_loops, swing, bpm, walking)
                drum_ev    += build_drums_v2(pat_a, sec_start, sec_bars, swing, bpm,
                                              fill_bars, energy_float)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                mel_ev     += build_melody_v2(key_root, sec_start, sec_bars, swing, bpm,
                                              'sparse', scale, motif=track_motif,
                                              progression=prog, prog_bars=prog_bars, section='A',
                                              markov_nodes=markov_nodes)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
                active_bars += sec_bars
                _tex = _SUBGENRE_TEXTURE.get(sub_genre)
                if _tex and random.random() < 0.50:
                    texture_ev += build_texture(_tex[0], prog, sec_start, sec_bars, swing, bpm, _tex[1])

            elif sec_label == 'BR':
                piano_ev   += build_chords_v2(prog, sec_start, n_loops, swing, bpm, ga_flag, optimizer_log)
                bass_ev    += build_bass_v2(prog, sec_start, n_loops, swing, bpm, walking)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                drum_ev    += build_break_hats(sec_start, sec_bars, swing, bpm)
                cmelo_ev   += build_counter_melody(break_key_root, sec_start, sec_bars, swing, bpm)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)

            elif sec_label == 'B':
                piano_ev   += build_chords_v2(prog, sec_start, n_loops, swing, bpm, ga_flag, optimizer_log)
                bass_ev    += build_bass_v2(prog, sec_start, n_loops, swing, bpm, walking)
                drum_ev    += build_drums_v2(pat_b, sec_start, sec_bars, swing, bpm,
                                              fill_bars, energy_float)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                mel_ev     += build_melody_v2(key_root, sec_start, sec_bars, swing, bpm,
                                              'medium', scale, motif=track_motif,
                                              progression=prog, prog_bars=prog_bars, section='B',
                                              markov_nodes=markov_nodes)
                if sec_bars > prog_bars:
                    cmelo_ev += build_counter_melody(key_root, sec_start + prog_bars,
                                                     sec_bars - prog_bars, swing, bpm)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
                active_bars += sec_bars
                _tex = _SUBGENRE_TEXTURE.get(sub_genre)
                if _tex and random.random() < 0.50:
                    texture_ev += build_texture(_tex[0], prog, sec_start, sec_bars, swing, bpm, _tex[1])

            elif sec_label == 'O':
                piano_ev   += build_chords_v2(prog, sec_start, n_loops, swing, bpm, ga_flag, optimizer_log)
                bass_ev    += build_bass_v2(prog, sec_start, n_loops, swing, bpm, False)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                cmelo_ev   += build_counter_melody(key_root, sec_start, sec_bars, swing, bpm)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
                od_bars = max(1, sec_bars // 2)
                od_raw  = build_drums_v2(pat_a, sec_start, od_bars, swing, bpm,
                                         energy=energy_float)
                n_od    = len(od_raw)
                od_raw  = [(ev[0], ev[1],
                            max(1, int(ev[2] * (1.0 - (i / max(1, n_od)) * 0.75))),
                            ev[3])
                           for i, ev in enumerate(od_raw)]
                drum_ev += od_raw
                if sec_bars - od_bars > 0:
                    drum_ev += build_intro_hats(sec_start + od_bars, sec_bars - od_bars, swing, bpm)

            cursor += sec_bars

        this_events = (piano_ev, bass_ev, drum_ev, mel_ev, pad_ev, cmelo_ev, texture_ev, sustain_ev)

        if score_track_quality is None:
            best_events, best_score = this_events, 1.0
            break

        try:
            score, failures = score_track_quality(mel_ev, piano_ev, drum_ev, active_bars, sub_genre)
        except Exception as e:
            print(f"  [quality] Scoring failed ({e}) — accepting attempt without gating")
            best_events, best_score, best_failures = this_events, 1.0, []
            break

        if score > best_score:
            best_events, best_score, best_failures = this_events, score, failures
        if score >= MIN_QUALITY_SCORE:
            break

    if best_score < MIN_QUALITY_SCORE and score_track_quality is not None:
        print(f"  [quality] Track scored {best_score:.2f} after {attempts_used} attempt(s) "
              f"(failures: {best_failures}) — using best attempt, not blocking upload")

    piano_ev, bass_ev, drum_ev, mel_ev, pad_ev, cmelo_ev, texture_ev, sustain_ev = best_events

    drum_ev = _apply_tension_to_drums(drum_ev, TOTAL, energy_mult)

    mid = mido.MidiFile(type=1, ticks_per_beat=PPQN)
    t0  = mido.MidiTrack()
    mid.tracks.append(t0)
    t0.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm), time=0))
    t0.append(mido.MetaMessage('time_signature', numerator=4, denominator=4,
                               clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
    t0.append(mido.MetaMessage('end_of_track', time=0))

    mid.tracks.append(abs_to_track(piano_ev, channel=0, program=piano_prog,
                                   cc_events=sustain_ev))
    bass_prog = _BASS_PROG_V2.get(sub_genre, GM_BASS)
    mid.tracks.append(abs_to_track(bass_ev, channel=1, program=bass_prog))
    drum_kit = random.choice(_SUBGENRE_DRUM_KITS.get(sub_genre, _DEFAULT_DRUM_KIT_POOL))
    mid.tracks.append(abs_to_track(drum_ev, channel=9, program=drum_kit,
                                   bank_msb=127 if drum_kit != 0 else None))
    if mel_ev:
        mid.tracks.append(abs_to_track(mel_ev,    channel=2, program=mel_prog))
    mid.tracks.append(abs_to_track(pad_ev,    channel=3, program=GM_STRINGS))
    if cmelo_ev:
        cmelo_prog = _cfg.get('cmelo', GM_WARM_PAD)
        mid.tracks.append(abs_to_track(cmelo_ev, channel=4, program=cmelo_prog))
    if texture_ev:
        tex_prog = _SUBGENRE_TEXTURE[sub_genre][0] if sub_genre in _SUBGENRE_TEXTURE else GM_WARM_PAD
        mid.tracks.append(abs_to_track(texture_ev, channel=5, program=tex_prog))

    # Feed this track's melody into the self-referential history (see
    # generate_music_gemini._build_self_markov / pick_params). Fires once, on
    # the winning attempt only — see build_midi()'s identical comment.
    _save_melody_pitch_classes([note % 12 for (_t, note, _v, _d) in mel_ev])
    try:
        _append_recipe_log(params, quality_score=best_score,
                            quality_retries=attempts_used - 1, ga_voicing=bool(ga_flag),
                            voicing_optimizer_wins=dict(Counter(optimizer_log)) if optimizer_log else None)
    except Exception:
        pass

    mid.save(output_path)
    return output_path


# ── 8. Entry points (same interface as v1) ──────────────────────────────────────

def generate_track(
    index: int = 0,
    concept_hint: str | None = None,
    genre_hint: str | None = None,
    song_dna: dict | None = None,
) -> str:
    print(f"\n[Track {index+1}] Picking parameters (v2)...")
    if song_dna is not None:
        params = dict(song_dna)
        params['drum_pattern_b'] = (params.get('drum_pattern_b', 3) + index) % len(DRUM_PATTERNS)
        params['swing'] = round(min(0.70, max(0.58, params.get('swing', 0.62) + random.uniform(-0.03, 0.03))), 2)
        print(f"  [DNA] bpm={params.get('bpm')} key={params.get('key')} sub={params.get('sub_genre')}")
    else:
        params = pick_params(concept_hint=concept_hint, genre_hint=genre_hint)

    with tempfile.TemporaryDirectory() as tmp:
        midi_path = os.path.join(tmp, 'track.mid')
        raw_wav   = os.path.join(tmp, 'raw.wav')

        print(f"  [MIDI v2] Building...")
        build_midi_v2(params, midi_path)
        chosen_sf = _pick_soundfont()
        print(f"  [FluidSynth] Rendering ({os.path.basename(chosen_sf)})...")
        midi_to_wav(midi_path, raw_wav, soundfont=chosen_sf)
        print(f"  [FX] Lo-fi chain ({params.get('sub_genre', '?')})...")
        ts  = int(time.time())
        out = os.path.join(MUSIC_DIR, f'track_{ts}_{index:02d}.wav')
        from scripts.lofi_fx import apply_lofi_fx as _lofi_fx
        _lofi_fx(raw_wav, out,
                 sub_genre=params.get('sub_genre'),
                 bpm=params.get('bpm', 80),
                 energy=params.get('drum_energy', 'medium'))

        try:
            from scripts.drum_sampler import layer_drum_break as _layer_drums
            print(f"  [DRUMS] Layering synthetic breaks ({params.get('sub_genre', '?')})...")
            _layer_drums(out, out,
                         bpm=params.get('bpm', 80),
                         sub_genre=params.get('sub_genre', 'chillhop'),
                         volume=0.22,
                         swing=float(params.get('swing', 0.62)))
        except Exception as _de:
            print(f"  [DRUMS] Skipped ({_de})")

        # Audio-domain quality gates on the final rendered WAV — see the
        # matching block in generate_music_gemini.generate_track() for the
        # full rationale (diagnostic only, never blocks/retries).
        try:
            import soundfile as _sf
            from scripts.track_quality import score_audio_quality
            _audio, _sr = _sf.read(out, dtype='float32')
            _audio_score, _audio_failures = score_audio_quality(_audio, _sr)
            print(f"  [audio-quality] score={_audio_score:.2f} failures={_audio_failures}")
            _append_audio_quality_log(out, _audio_score, _audio_failures)
        except Exception as _aqe:
            print(f"  [audio-quality] Scoring skipped ({_aqe})")

    with open(out + '.meta.json', 'w', encoding='utf-8') as _mf:
        json.dump({'title': params.get('mood', 'lofi dreams'),
                   'genre': params.get('sub_genre', 'lo-fi hip hop')}, _mf)

    print(f"  ✓ {out} ({os.path.getsize(out)//1024//1024} MB)")
    return out


def generate_tracks(
    count: int = 3,
    concept_hint: str | None = None,
    genre_hint: str | None = None,
    song_dna: dict | None = None,
) -> list[str]:
    import concurrent.futures
    print(f"[MUSIC v2] Generating {count} track(s)...")

    if song_dna is None and count > 1:
        param_sets = _build_diverse_params(count, concept_hint, genre_hint)
        print(f"  [MUSIC v2] Track plan: {' → '.join(p['sub_genre'] for p in param_sets)}")
    else:
        param_sets = None

    workers = min(count, 3)
    paths   = []

    def _run(i: int) -> str:
        dna   = param_sets[i] if param_sets else song_dna
        chint = None if param_sets else concept_hint
        ghint = None if param_sets else genre_hint
        return generate_track(i, concept_hint=chint, genre_hint=ghint, song_dna=dna)

    if workers <= 1:
        for i in range(count):
            try:
                paths.append(_run(i))
            except Exception as e:
                print(f"  [ERROR] Track {i}: {e}")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_run, i): i for i in range(count)}
            for fut in concurrent.futures.as_completed(futs):
                i = futs[fut]
                try:
                    paths.append(fut.result())
                except Exception as e:
                    print(f"  [ERROR] Track {i}: {e}")

    print(f"\n[MUSIC v2] {len(paths)}/{count} tracks ready.")
    return paths


if __name__ == '__main__':
    import sys as _sys
    n = int(_sys.argv[1]) if len(_sys.argv) > 1 else 1
    generate_tracks(n)
