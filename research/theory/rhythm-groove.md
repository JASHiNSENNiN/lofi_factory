# Rhythm & Groove — Research Notes

Scope: extending the drum-rhythm generation shared by `scripts/euclidean.py`
(`bjorklund`), `scripts/drum_sampler.py` (audio layer), and
`scripts/generate_music_gemini.py` (MIDI layer — `generate_euclidean_drum_pattern`,
`generate_ca_drum_pattern`, `DRUM_PATTERNS` A–P, `DRUM_FILLS`, `_EUCL_HATS`,
`grid_tick`/`jitter`/`v`/`_gauss_jitter`/`_gauss_velocity`/`_lofi_late`). This
codebase already implements Euclidean rhythms with backbeat rotation-search
and IOI velocity weighting, four Wolfram CA rules driving kick/snare/hat
generation, Gaussian and uniform humanization, MPC-style swing quantization,
and 16 hand-authored patterns including a tresillo/cinquillo/clave family
generalized via `_EUCL_HATS`. The gaps are narrower than a first glance
suggests — this doc targets them specifically.

## Swing quantization: the actual math

MPC-style swing delays only the even-numbered 16th notes (the "and" of each
8th-note pair); the percentage is literally where that delayed note lands as
a fraction of the 8th-note span. Roger Linn, who designed the original
Linn/Akai swing engine, states it plainly: "I merely delay the second 16th
note within each 8th note... I delay all the even-numbered 16th notes" — 50%
means no delay (straight), 66% is "perfect triplet" (first 16th gets 2/3 of
the pair's duration, second gets 1/3)
([Attack Magazine, Roger Linn interview](https://www.attackmagazine.com/features/interview/roger-linn-swing-groove-magic-mpc-timing/)).
Values in between (54%, 58%, 62%) are non-triplet "loosening" that breaks
mechanical stiffness without reading as full swing
([About MPC Swing](https://palsen.tumblr.com/post/182157488304/about-mpc-swing)).

This repo's `grid_tick(grid_16th, swing)` (generate_music_gemini.py:1039) and
`_build_loop`'s `swing_off` (drum_sampler.py:285) already implement exactly
this formula — `swing` as a 0–1 float *is* the MPC percentage (0.5 = 50%,
0.66 = 66% triplet), and both layers derive the offset from the same input so
MIDI and audio drums share a pocket. Concretely, at 90 BPM (16th = 166.7 ms)
the repo's `lofi_drill` swing range (0.63–0.74) delays the even 16th by
43–80 ms; `bossa_lofi` (0.52–0.60) delays it by only 3–33 ms — a ~15–20×
spread in raw milliseconds despite looking like a small range as a float.
Because the offset scales with 16th-note duration, the same swing float
produces a larger ms offset at slower BPM and smaller at faster BPM — swing
feel is tempo-relative, not an absolute ms constant.

## Boom-bap conventions (relevant to patterns A/B/G already in `DRUM_PATTERNS`)

Snare on 2 and 4 is the defining boom-bap backbeat, inherited from the
breakbeat tradition; kicks typically land on 1 plus a syncopated pickup
around beat 3 ("1, 4th 8th-note, 6th 8th-note" per production guides), not
four-on-the-floor
([RouteNote boom-bap guide](https://create.routenote.com/blog/how-to-make-90s-hip-hop-boom-bap-drums/),
[Native Instruments](https://blog.native-instruments.com/what-is-boom-bap/)).
Hi-hats quantized to 8ths (not 16ths) is called out as the classic boom-bap
hat density — patterns G and L already use denser 16th-hat grids, closer to
hip-hop-tight/trap than strict boom-bap; pattern A's `CHH` (8th-dominant with
16th ghosts) is closer to the source convention. "Ghost kicks" fall just
before the main kick/snare at reduced velocity for the "ba-boom" feel —
distinct from ghost *snares*, and not framed as a deliberate pickup anywhere
in the current patterns (kick ghost hits exist, e.g. C and F, but aren't
positioned as pre-kick pickups specifically).

## Ghost notes: velocity range and placement

Ghost notes sit at roughly velocity 10–22 (0–127 scale) — meaningfully
quieter than the 25–52 range several `DRUM_PATTERNS` entries use for their
softest snare hits (B's 38/35, C's 36/32, I's 30/32/35)
([Soundbrenner](https://www.soundbrenner.com/blogs/articles/ghost-notes),
[DRUM! Magazine](https://drummagazine.com/lesson-ghost-note-style-and-placement/)).
The most common hip-hop/house placement is the 16th right after beat 1 (step
1, 0-indexed), leading into the snare on beat 2 — not currently privileged in
the table's ghost-snare steps, which cluster around steps 7, 9, 14
(before/after the backbeat) rather than right after beat 1. Three-to-four
ghosts per bar is cited as the sweet spot versus constant 16ths, matching the
current patterns' density well.

## Humanization: Gaussian vs. uniform, and Dilla's "off" grid

The repo's `_gauss_jitter`/`_gauss_velocity` (sigma-clustered, capped ±1.5×)
versus `jitter`/`v` (flat uniform `random.uniform`/`randint`) split maps onto
documented practice: Ableton's Random groove parameter and Logic's
groove-template "Random" add small clustered-not-flat deviations for a human
feel without destroying the underlying grid
([Sound on Sound, Logic quantize/groove](https://www.soundonsound.com/techniques/quantisation-groove-functions-logic)),
and groove-humanization guidance generally describes deviations as "a few
milliseconds forward or backward" clustered near the target, not spread
uniformly. `_gauss_jitter`/`_gauss_velocity` are currently used selectively
(melody/chords/bass, per the code comment at line 1052) but not wired into
`build_drums`, which still uses the flatter `jitter`/`v` pair — a real,
checkable gap.

J Dilla's signature "drunk" feel came specifically from disabling MPC3000
quantization entirely rather than applying a bounded jitter — genuinely
off-grid placement, not a small deviation around a target
([Sampleface, "How J Dilla Humanized the MPC3000"](https://sampleface.co.uk/how-j-dilla-humanized-the-mpc3000/)).
Pattern C ("J Dilla drunk") in `DRUM_PATTERNS` already encodes this as
hand-placed off-grid velocities (kick on step 3, a 16th early) rather than as
a wider-variance jitter function — consistent with the real technique, since
Dilla's "drunk" feel was compositional/placement-based, not a randomization
parameter turned up. `_lofi_late` (mean +17ms, std 4ms) models a different,
narrower phenomenon: systematic "behind the beat" laid-back feel, currently
melody-only.

## Polyrhythm and additive rhythm

A 3-over-4 polyrhythm/hemiola superimposes 3 equal-spaced hits over a span
metrically felt as 4 (or 2), producing hi-hat/snare ostinatos independent of
the kick's pulse
([Not So Modern Drummer, polyrhythm basics](https://www.notsomoderndrummer.com/not-so-modern-drummer/2017/2/14/3mc7w3owvfkb0hp2um1zbbzm75dltm)).
`_EUCL_HATS['tresillo']` (E(3,8)×2) and pattern M's explicit 3+3+2 grouping
already cover the additive-rhythm case described in this research — nothing
new to recommend there beyond confirming it's covered. A true 3-over-4
*cross-rhythm* (independent 3-pulse layer against the 4/4 kick, not folded
into one 16-step additive grouping) is not currently represented and is a
distinct technique from what's implemented.

## Genre cells: dembow, phonk rolls, drill triplets

**Dembow** (reggaeton) is a tresillo-family pattern too — kick on beats 1 and
the "and" of 2, snare/rimshot on the "and" of 1 and downbeat of 3 over a
two-bar phrase, or equivalently snares on 16th-steps 4, 7, 12, 15 with kicks
on all four quarter notes
([Orphiq, dembow explained](https://orphiq.com/resources/what-is-dembow),
[MusicRadar reggaeton tips](https://www.musicradar.com/tuition/tech/23-reggaeton-tips-33748)).
Being tresillo-derived, it's reachable via a `_EUCL_HATS`-style rotation of
the existing `tresillo` cell rather than new machinery — a natural fit for
`lofi_world` (already has an elevated swing range, 0.58–0.68, "organic
percussive feel, not stiff-straight" per its own comment) rather than the
trap-leaning subgenres.

**Phonk** hi-hats start from straight 8th/16th patterns and layer in
32nd/64th-note *rolls* for variation and dynamic velocity-shaped texture,
plus a pitched-cowbell layer as a genre-defining voice distinct from hats
([Melodics phonk producer's guide](https://melodics.com/blog/producers-guide-to-phonk-music)).
This is absent from current `lofi_phonk` handling — pattern L / `_PAT_808_TRAP`
give uniform 16th hats, no density-building roll or cowbell-equivalent voice.
`generate_ca_drum_pattern`'s rule-90 hat path (chosen for "denser texture")
is the closest existing building block for a burst effect but isn't tuned
for the specific roll shape.

**Drill** hi-hats are triplet subdivisions layered over the underlying 16th
grid — a genuinely different subdivision, not just a denser 16th pattern —
alongside the sliding-808 bassline as drill's single most recognizable
element ("Chicago drill... double-time hi-hat triplets... UK drill employs
rapid triplet patterns," [Orphiq drill guide](https://orphiq.com/resources/what-is-drill-music);
grime-derived "two-two-one" 16th-grid base with triplet flourishes,
[Amped Studio drill guide](https://ampedstudio.com/blog/what-is-drill-music/)).
Pattern P ("Drill bounce") nails the offbeat kick and back-half hat-density
build, but it's still on the 16-step grid — true drill triplet hats need a
12-step-per-bar (8th-note-triplet) subdivision layered against the existing
16-grid kick/snare, which the fixed 16-step `DRUM_PATTERNS` architecture
doesn't support without a parallel triplet-grid event path.

## Microtiming research: is jitter definitely good?

The literature is more contested than "humanize = better" suggests. Charles
Keil's Participatory Discrepancies (PD) theory — extended by Vijay Iyer's
1998 dissertation on embodied cognition in African-American groove music —
holds that small (~±50ms) timing deviations are what create "groove," but
controlled listening studies found mixed results: some samba/funk/jazz
tracks with real microtiming deviations were rated as grooving *less* than
perfectly quantized versions
([PMC, microtiming and groove in jazz](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6934603/),
[PMC, expert microtiming and listener experience](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5050221/)).
Practical takeaway: `_gauss_jitter`'s sigma-of-a-few-ms, clustered-not-flat
approach is closer to what the literature treats as "idiomatic/structural"
microtiming than a wide flat `jitter()` spread — a reason to migrate
`build_drums` onto `_gauss_jitter`/`_gauss_velocity` rather than just
widening the existing jitter range.

## Concrete additions

| table/function to extend | proposed entries | rationale |
|---|---|---|
| `DRUM_PATTERNS` | Add pattern Q: phonk hat-roll cell — straight 8th/16th base hat with a 32nd-note roll burst on the last quarter of the bar (steps 13–16 subdivided), plus a pitched-cowbell-style rim/perc voice on the "and" of 2 and 4 | Melodics guide describes phonk hats as base pattern + 32nd/64th roll for variation, with cowbell as a defining separate voice — neither exists in current `lofi_phonk` handling (`_PAT_808_TRAP`/pattern L are uniform 16ths) |
| `_EUCL_HATS` | Add `dembow` preset via rotation of the existing `tresillo` cell (kick-equivalent onsets on steps 0, 6; snare-equivalent on steps 2, 8 in a 16-step bar) | Dembow is documented as tresillo-derived, not a new rhythmic primitive — reachable by rotating/relabeling the cell already in the table rather than adding new generation logic; natural fit for `lofi_world`'s existing "organic percussive" swing range |
| `build_drums` (generate_music_gemini.py:1130) | Swap the flat `jitter()`/`v()` calls for `_gauss_jitter()`/`_gauss_velocity()`, matching what melody/chords/bass already do | Sigma-clustered timing deviation is what the microtiming literature (Keil/Iyer PD framework, PMC groove-perception studies) treats as "idiomatic" feel; a flat-uniform spread is the kind of deviation pattern controlled studies found *didn't* improve groove ratings |
| `generate_ca_drum_pattern` | Add rule 60 or rule 126 to `_CA_RULE_POOL` for hat texture specifically, evaluated for whether their generation output naturally clusters into 32nd-note-density bursts (a phonk-roll-like shape) rather than even density | Rule 90's Sierpinski/XOR output is already chosen for "denser texture" but isn't shaped like phonk's roll-then-rest burst pattern; worth testing whether another elementary rule's growth curve better matches that specific shape before hand-authoring pattern Q's roll numerically |
| `DRUM_PATTERNS` | Add a drill-triplet variant of pattern P expressed on a 12-step (8th-note-triplet) sub-grid for CHH only, layered against the existing 16-step kick/snare — requires a small `build_drums` extension to accept a per-voice grid divisor | Drill's hi-hat triplets are a genuinely different subdivision (12 vs 16 per bar), not reachable by making the 16-step hat pattern denser — pattern P currently approximates the *density build* correctly but not the *triplet* feel itself |
| `_SWING_RANGE` | Consider whether `lofi_phonk` (0.62–0.73) needs a companion "roll density" parameter distinct from swing, since phonk's characteristic bounce comes more from the hat-roll shape than from 16th-note swing offset | Melodics guide frames phonk's "loose" feel as coming from swing *and* off-grid hat placement *and* roll density as three separate levers; the repo currently only varies the first |
