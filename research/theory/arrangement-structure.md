# Arrangement & Song-Form Research: Where the Generator's Structure Model Has Room to Grow

This note surveys lofi/chillhop/phonk arrangement convention against what `generate_music_gemini.py` already
implements — `_SONG_FORMS`, `generate_song_form()`'s grammar, `_bridge_progression()`, `_SCALE_MODAL_LIFT`, and
`build_texture()` — to find genuine gaps rather than re-argue settled ground.

## 1. Section proportions and the existing forms hold up well

Lofi convention describes a loop-first arrangement: intro (~8–16 bars), main groove (~16–32 bars), an 8-bar
breakdown, a 16-bar "variation" section, and an 8–16 bar outro, built by bringing elements in and out in 4–8 bar
phrases rather than through big EDM-style drops — see the [beatsbypao anatomy-of-a-song walkthrough](https://www.beatsbypao.com/l/anatomy-of-a-song-understanding-the-song-structure/)
and the general production-guide consensus summarized across [audioplugin.deals](https://audioplugin.deals/blog/the-ultimate-guide-to-lofi-hip-hop-production/),
[EDMProd's lofi guide](https://www.edmprod.com/lofi-hip-hop/), and [Native Instruments' lofi blog](https://blog.native-instruments.com/lo-fi-hip-hop-beats/).
`_SONG_FORMS['standard']` (`I:1, A:4, BR:1, B:4, O:1`) is a near-exact match to this pattern once "loops" are read
as multi-bar progression cycles rather than single bars.

More usefully, [Richard Pryn's structure breakdown](https://richardpryn.com/lofi-music-structure/) analyzes three
real lofi tracks by their loop-letter sequence — ABABB (Marsquake & Sátyr), AB-AB-ABC (Jinsang), ABBABBA (Eevee)
— i.e. producers freely vary how many times A and B alternate and repeat rather than sticking to one template.
This is precisely what `generate_song_form()`'s `I ('A' break? 'B')+ O` grammar already generates: variable-count
A/B alternation with optional breaks. The grammar isn't a nice-to-have alternative to the curated forms — it's
independently corroborated by how real lofi producers actually arrange tracks. No gap here.

## 2. Duration: the codebase's total-loop ranges track real-world convention

Standard lofi beats run **1–3 minutes**, with **~2 minutes** the most common single-track length; longer
"extended" pieces run 3–10 minutes and are typically slower ([sakuknight's duration breakdown](https://www.sakuknight.com/post/lofi-music-durations),
also echoed by [Richard Pryn](https://richardpryn.com/lofi-music-structure/)). Sakuknight's stated reason is
functional, not aesthetic: lofi is designed as loopable background/study music, so tracks stay short enough to
loop cleanly for that use case, unlike pop's fixed 3–4 minute commercial-radio convention. This validates the
existing form-length spread (5 loops for `minimal` up to 20-loop grammar cap for long/extended forms) as roughly
the right order of magnitude — no evidence for extending the cap further.

## 3. Genuine gap #1: section-boundary transition FX are entirely unmodeled

Nothing in `_SONG_FORMS`, `generate_song_form()`, or `_bridge_progression()` encodes *how* one section hands off
to the next — only *how long* each section is. Lofi/hip-hop production leans heavily on a small, well-defined
transition vocabulary at section boundaries:

- **Vinyl stop/brake** — the record decelerating to a halt, used as a hard cut between sections
  ([Splice's lofi production interview](https://splice.com/blog/lo-fi-beat-origin-sound/), [Lofi Music Academy on vinyl/tape effects](https://www.lofimusicacademy.com/the-art-of-vinyl-tape-effects-in-lofi-music-production)).
- **Reverse cymbal / riser swells** — a reversed crash or white-noise riser pulling the listener *into* the next
  section rather than pushing toward it, standard across hip-hop/electronic/cinematic transitions
  ([Point Blank on reversals](https://www.pointblankmusicschool.com/blog/using-reversals-to-create-unique-transitions-in-your-tracks/)).
- **Filter sweeps** (low-pass into a breakdown, high-pass building out of one) layered with riser/snare-roll
  builds — the standard three-tool transition kit, with the caveat that over-using all three at once reads as
  predictable ([Point Blank on risers/FX](https://www.pointblankmusicschool.com/blog/designing-unique-risers-and-fx-for-transitions-to-level-up-your-tracks/)).

This is a clean, orthogonal axis to add: a small lookup keyed by the `(from_label, to_label)` pair the form tuples
already produce, independent of the loop-count logic.

## 4. Genuine gap #2: "arrangement by subtraction" is coarser than production convention

`build_texture()` currently fires a whole secondary layer at a flat 50% probability *per track*, and
`_SCALE_MODAL_LIFT` handles harmonic lift on breakdowns — but neither varies *density* by section. Real
subtractive arrangement is a per-section mute/unmute discipline: strip kick and bass in a buildup or breakdown to
create anticipation, keep only a minimal element, then reintroduce everything at the return so it lands with more
impact than if nothing had ever left ([Serato's arrangement-tips piece](https://the-drop.serato.com/how-to/song-arrangement-tips-for-beat-makers/),
[Cookingtechno's "escape the loop" guide](https://cookingtechno.com/escape-the-loop/)). The generator's texture
layer is currently binary per whole render rather than probabilistically denser on `A`/climactic sections and
sparser on `BR`/`B` sections — a straightforward, low-risk extension (see table below).

## 5. AABA is a real, distinct archetype the codebase is missing for its jazz-rooted subgenres

AABA (32-bar jazz standard form: two A statements, a contrasting B "bridge" that typically shifts to the
subdominant or relative minor, then a final A) is the defining structural convention of the jazz-standard
repertoire the codebase's `bossa_lofi`, `jazz_cafe`, and `lofi_jazz` subgenres draw from
([Jazzfuel's AABA explainer](https://jazzfuel.com/aaba-song-form/), [Wikipedia: thirty-two-bar form](https://en.wikipedia.org/wiki/Thirty-two-bar_form)).
Notably, `bossa_lofi` and `jazz_cafe` are currently **absent from `_FORM_BY_SUBGENRE`** and silently fall back to
`'standard'` — a generic I-A-BR-B-O shape with no structural nod to the AABA convention their harmonic engine
(`_bridge_progression()`, already built for real reharmonization) is otherwise well-suited to express.

## 6. Phonk/drill are foreground, buildup-driven genres — not wallpaper music

Ambient's founding philosophy (Eno's *Music for Airports*, built from tape loops of deliberately mismatched
lengths that phase in and out of sync so no combination repeats inside a normal attention span) explicitly treats
lofi/ambient as music meant to reward *both* foreground and background listening without ever demanding attention
via a hook or drop ([overview of ambient/furniture-music philosophy](https://oboe.com/learn/introduction-to-ambient-music-creation-4qo83h/composition-and-arrangement-6)).
That's the right model for `ambient`/`piano_lofi`/`vaporwave`. It is explicitly the *wrong* model for
`lofi_drill` and `lofi_phonk`, both of which currently have **no entry in `_FORM_BY_SUBGENRE`** and fall back to
the generic forms. Phonk/drill structure is buildup-and-release: short intro, energy escalated via low-pass/
high-pass filter automation into a "drop," syncopated cowbell/808 layers driving relentless forward energy rather
than drifting ([Melodics' phonk production guide](https://melodics.com/blog/producers-guide-to-phonk-music), [EDMProd's phonk how-to](https://www.edmprod.com/how-to-make-phonk/),
[drift-phonk genre overview](https://www.melodigging.com/genre/drift-phonk)). Tracks stay brief (1–2 minutes)
with variation delivered by swapping layers every 8–16 bars rather than by long dreamy modal drift. Important
honest caveat: a *literal* drop (a genuine energy discontinuity, not just a different chord) is not expressible
in the current `(label, num_prog_loops)` tuple format at all — that format encodes structure and duration only,
never per-section intensity/density. The concrete addition below approximates a buildup/drop *feel* using only
existing labels (repeated `BR`→`A` buildup-release cycles instead of one `BR`→`B` breakdown), and separately flags
where a genuinely new label would be required if true intensity-curve modeling is wanted later.

## Concrete additions

| table/function to extend | proposed entries | rationale |
|---|---|---|
| `_SONG_FORMS` | `'aaba': [('I',1),('A',2),('A',2),('BR',2),('A',2),('O',1)]` (10 loops) | Matches the canonical AABA jazz-standard shape (§5) — two A statements, a contrasting bridge, a final A — using only existing labels (`BR` doubling as the "B"/bridge section, consistent with how `_bridge_progression()` already reharmonizes `BR`). |
| `_SONG_FORMS` | `'build': [('I',1),('A',3),('BR',1),('A',3),('BR',1),('A',3),('O',1)]` (13 loops) | Approximates phonk/drill's buildup→release cycling (§6) with existing labels: `BR` repurposed as a short filtered-buildup section immediately preceding a return to full-energy `A`, instead of the ambient-style single mid-track breakdown the other forms use. No `B` section at all — phonk/drill arrangement is repetition-with-layer-swap, not a long contrasting drop-down section. |
| `_FORM_BY_SUBGENRE` | `'bossa_lofi': 'aaba'`, `'jazz_cafe': 'aaba'` | Both are currently unmapped and silently default to `'standard'` despite being the two subgenres most directly rooted in the jazz-standard tradition that defines AABA (§5). |
| `_FORM_BY_SUBGENRE` | `'lofi_drill': 'build'`, `'lofi_phonk': 'build'` | Both are currently unmapped (default to `'standard'`/generic grammar). Phonk/drill are structurally the furthest genre in this codebase's subgenre list from lofi's ambient/wallpaper-music premise (§6) and deserve their own archetype rather than inheriting the same breakdown-centric shape as `ambient`/`piano_lofi`. |
| new dict, e.g. `_SECTION_TRANSITION_FX` keyed by `(from_label, to_label)` | e.g. `('A','BR'): 'filter_lowpass_sweep'`, `('BR','A'): 'vinyl_stop'` or `'reverse_riser'`, `('B','O'): 'filter_lowpass_sweep'` | Section-boundary FX (vinyl stop, reverse riser, filter sweep) are a well-documented, distinct layer of lofi/hip-hop production (§3) that the current form tuples don't touch at all — they only encode duration, not the handoff between sections. |
| `build_texture()` call site / new `_SECTION_TEXTURE_DENSITY` dict keyed by label | e.g. `{'I':0.3,'A':0.6,'BR':0.25,'B':0.4,'O':0.2}` replacing the flat 50% probability | Real subtractive arrangement varies density by section (strip layers into breakdowns, restore at the return) rather than rolling once per whole track (§4) — a low-risk generalization of the existing per-track coin-flip into a per-section one. |
| *(flagged, not proposed)* a new label, e.g. `'C'` for climax/drop | — | Only worth adding if a *true* discontinuous-intensity drop (not just a chord/section change) is wanted for `lofi_drill`/`lofi_phonk` — the current `(label, loop_count)` shape has no field for intensity, so `'build'` above is a structural approximation, not the real thing (§6). |
