# Melody Techniques — Research Notes

Scope: melody-generation techniques for extending `build_melody()`,
`generate_motif()`, and `vary_motif()` in `generate_music_gemini.py`.

## What the codebase already has

`build_melody()` (line ~1390) already implements: a phi-point (0.618)
contour arc — ascending-biased steps before the golden-ratio point, then
descending-biased after; chord-tone snapping on 60% of phrase-first-notes via
`_chord_pcs_at_bar`; tension-weighted step-size selection
(`random.choices([-1,0,1,2], weights=[2,2,3,1+3*tension])`); grace-note
acciaccatura (one scale-degree below, 15% chance, on phrase-first notes
only); Markov-nudged pitch-class biasing from a learned source melody
(`markov_nodes`); and Gaussian humanized timing/velocity. `generate_motif()`
picks a 3-5 note motif via constrained random walk (`[-2,-1,-1,0,1,1,2]`
scale-degree steps). `vary_motif()` implements **retrograde**, **inversion**
(reflected around the motif's first note, clamped to scale range),
**transpose_up** (one scale degree), and a **default** nudge variant — so
retrograde/inversion/transposition are already covered; augmentation
(duration stretching) and fragmentation (using a sub-slice of the motif) are
not. There is no explicit call-and-response mechanism between the main
melody and `build_counter_melody()` (they're generated independently, not as
question/answer pairs), and note selection is scale-index-random rather than
weighted by chord-tone-vs-passing-tone status (the *snap* at phrase-start is
the only chord-awareness; interior notes are unweighted).

## Constraint-based generation (scale/chord-tone/contour/leap)

Academic constraint systems typically layer three constraint classes:
functional (valid chord-to-chord relationships), melodic-compatibility
(notes fit the current chord), and voice-leading (bounded interval jumps
between consecutive notes)
([arxiv 2512.07627, symbolic transformer melodic harmonization](https://arxiv.org/html/2512.07627)).
A simpler, directly-portable pattern from patent/DSP literature: assign
scale-degree weights that favor chord tones over passing tones (e.g. chord
tones weight 6, scale passing tones weight 4, out-of-scale near-zero), then
sample the next note from a weighted-random choice rather than uniform scale
index ± step — and additionally gate *leap size* on whether the current note
is a chord tone: wide jumps permitted from chord tones, restricted from
passing tones
(patent excerpt via [USPTO 5099740](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/5099740)).
This is a direct upgrade path for `build_melody()`'s interior-note selection,
which currently applies chord-awareness only at phrase-start.

## Call-and-response phrasing

Call-and-response pairs a "call" phrase with an "answering" phrase that
differs in register, dynamics, or rhythm but relates motivically — often by
starting identically and diverging ("question and answer"/"parallel
period"), or by echoing the call an octave away
([MasterClass call and response](https://www.masterclass.com/articles/what-is-call-and-response-in-music),
[LANDR call and response](https://blog.landr.com/call-and-response/)). The
repo's `build_counter_melody()` (line ~1591) is architecturally positioned
to be this — it plays in `key_root - 12` register and is described as
"answering melody in lower register... fills silence between main melody
phrases" — but it draws from `get_pentatonic()` independently rather than
deriving its phrase content from the actual motif the main melody just
played. True call-and-response would pass the main melody's last phrase (or
`vary_motif(motif, ..., 'invert')`/octave-down transposition of it) into the
counter-melody builder as its motif seed, so the "answer" is recognizably
related to the "call" rather than merely co-located in time.

## Motif development: augmentation and fragmentation (the two gaps)

Beyond the four techniques already in `vary_motif()`, the two classical
thematic-transformation techniques absent are **augmentation** (stretching
note durations, e.g. doubling every note's `dur`) and **fragmentation**
(extracting and repeating a short sub-cell of the motif, e.g. just its first
2 notes) — both catalogued alongside retrograde/inversion as Liszt/Berlioz-era
"thematic transformation" techniques still standard in composition pedagogy
([Wikipedia thematic transformation](https://en.wikipedia.org/wiki/Thematic_transformation),
[Vaia motif development](https://www.vaia.com/en-us/explanations/music/music-composition/motif-development/)).
Diminution (the durational inverse of augmentation — compressing note values)
is the natural companion and equally absent. Because `vary_motif()` only
returns a *pitch* sequence (durations are assigned later in `build_melody()`
per-note independently), augmentation/diminution would need to act at the
`dur = int(BAR * random.uniform(...))` call site instead of inside
`vary_motif()` itself — e.g. an `'augment'` variation flag that scales the
`0.22-0.72` duration-fraction range up, and a `'fragment'` variation that
returns `motif[:2]` or `motif[-2:]` repeated instead of the full motif.

## Chord-tone-weighted note selection

Beyond the constraint-literature weighting above, a second concrete pattern:
initial/strong-beat pitches drawn from chord tones with passing/neighbor
tones filling weak-beat gaps, and *wide leaps permitted only when leaving a
chord tone* — mirroring classical strict-counterpoint practice
([USPTO 6100462 melody generation apparatus](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/6100462),
[soundquest step-or-skip](https://soundquest.net/melody/m-1/step-or-skip/)).
Concretely for `build_melody()`: the `step = random.choices(...)` block
(line ~1473) could consult `_chord_pcs_at_bar` on every note, not just
phrase-starts, and widen the `[-2,-1,0]`/`[-1,0,1,2]` weight envelope when
the *current* note (not just the phrase-start) lands on a chord tone.

## Grace notes / ornamentation

Two grace-note types: **appoggiatura** (takes rhythmic value from the main
note — a strong-beat "leaning" dissonance that resolves) and
**acciaccatura** (crushed in before the beat, main note keeps its full
value) — jazz treats both loosely, often as "crushed" grace-note pairs
played almost simultaneously with the main note
([MasterClass grace notes](https://www.masterclass.com/articles/grace-notes-guide),
[Wikipedia grace note](https://en.wikipedia.org/wiki/Grace_note)). The repo
already implements a scale-step-below acciaccatura at 15% chance on
phrase-first notes (line ~1513). Missing idiomatic variants: an
**upper-neighbor** grace note (scale step *above*, not just below — common
in jazz "surround" ornamentation), a **chromatic** approach tone (half-step
below regardless of scale membership — very idiomatic in bebop-adjacent
lofi/jazz melody and currently impossible since the code only picks from
`notes_scale`), and a **double-grace** (two quick notes approaching from
opposite sides, i.e. a turn figure) for climax-note emphasis near the
phi-point.

## Melodic contour / shape constraints

Four canonical contour shapes: ascending, descending, static, and arch (rise
to a peak near/before the midpoint, then descend) — arch is the default
"satisfying" phrase shape, evoking tension building to a climax and release
([Fiveable melodic contour](https://fiveable.me/ap-music-theory/key-terms/melodic-contour),
[aboutmusictheory melody shape](https://www.aboutmusictheory.com/melody-shape.html)).
`build_melody()`'s phi-point logic (ascend before 0.618, descend after) is
already a form of arch contour, just asymmetric (peak later than the
geometric midpoint, which is itself a deliberate, well-documented
composition choice — the golden-ratio climax point). A concrete addition
would be occasionally alternating this default arch with an **inverted arch**
(descend-then-ascend, useful for a "question" phrase that a call-and-response
answer resolves upward) and a **static** contour (small step range throughout,
no leap-biasing) for the sparsest densities, giving contour variety beyond
the single hard-coded arch shape.

## Leap vs. step motion

Rule of thumb: stepwise motion should outnumber leaps by at least 2:1, and
any leap of a third or larger should typically be followed by stepwise
motion in the *opposite* direction (leap up → step down, and vice versa) to
keep the line balanced and singable
([secretsofsongwriting melodic leaps](https://www.secretsofsongwriting.com/2022/01/31/writing-song-melodies-be-careful-with-melodic-leaps/),
[Robin Hoffmann steps and leaps](https://www.robin-hoffmann.com/dfsb/melodic-steps-and-leaps/)).
`build_melody()`'s step-choice weights (`[-1,0,1,2]` pre-climax,
`[-2,-1,0]` post-climax) do not enforce direction-reversal after a leap —
each note's step is chosen independently of whether the *previous* step was
itself a leap. Adding a one-step lookback (if `abs(prev_step) >= 2`, bias the
next `step` toward the opposite sign) would bring the existing logic in line
with this well-established resolution convention without changing the
overall phi-point architecture.

## Lofi/jazz-specific melody idioms

Genre sources converge on: small motifs and repeating phrases over
over-composed lead lines, human-feel timing (already covered by
`_gauss_jitter`/`_lofi_late`), and swing-driven phrasing rather than
strict-grid placement
([EDMProd lofi hip hop](https://www.edmprod.com/lofi-hip-hop/),
[Mixed In Key lofi guide](https://mixedinkey.com/captain-plugins/wiki/how-to-make-lofi-hip-hop/)).
Nothing here indicates a gap the code doesn't already address — this
confirms the existing sparse/dense density toggle and motif-repetition
architecture in `build_melody()` is genre-appropriate, not a rediscovery
target; the interesting deltas are in constraint precision (chord-tone
weighting, leap resolution) covered above, not in overall philosophy.

## Concrete additions

| table/function to extend | proposed entries | rationale |
|---|---|---|
| `vary_motif()` | new `variation == 'augment'`: return `motif` unchanged in pitch but flag duration-scale ×1.5-2 for the caller to apply at the `dur = int(BAR * random.uniform(0.22, 0.72))` site in `build_melody()` | classical augmentation technique, currently absent; needs a duration-scale return value or a companion `dur_scale` dict keyed by variation name |
| `vary_motif()` | new `variation == 'fragment'`: `return motif[:2] * 2` (repeat first 2 notes) or `motif[-2:]` for a tail-fragment variant | fragmentation is a standard Liszt/Berlioz-era technique cataloged alongside retrograde/inversion; currently the only "shortening" behavior is `phrase_len = len(phrase_notes)` with no sub-motif option |
| `VARIATIONS` list (line 1447) | extend `['retrograde','transpose_up','invert','default','default']` to `['retrograde','transpose_up','invert','augment','fragment','default','default']` | wires the two new variations into the existing round-robin selection with the same weighting style already used |
| `build_melody()` step-choice block (~line 1473) | add one-step lookback: `if abs(prev_step) >= 2: step = -sign(prev_step) * random.choice([1,2])` before applying the existing `random.choices` weighting | enforces documented leap-then-step-reversal convention; requires tracking `prev_step` across the note loop (currently untracked) |
| `build_melody()` grace-note block (~line 1513) | add a second grace-note mode: `if random.random() < 0.08: grace_note = note - 1` (chromatic, bypassing `notes_scale`) as an alternative to the existing scale-step-below acciaccatura | chromatic approach tones are idiomatic in jazz/lofi ornamentation and currently impossible since grace notes are drawn only from `notes_scale` |
| `build_counter_melody()` (~line 1591) | accept an optional `seed_motif` param; when provided, call `vary_motif(seed_motif, notes_low, 'invert')` or octave-shift it instead of drawing fresh notes from `get_pentatonic(key_root - 12)` | turns the existing independent counter-melody into a true call-and-response answer derived from the main melody's actual motif |
| `build_melody()` interior note-selection (~line 1478-1480) | when `i > 0`, also snap toward `chord_pcs` with a lower probability (e.g. 25% vs. the phrase-start's 60%), not just at `i == 0` | extends chord-tone awareness beyond phrase-start-only, matching the "chord tones on strong beats" pattern documented above |
