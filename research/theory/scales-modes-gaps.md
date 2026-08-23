# Scales & Modes — Gap Analysis

Scope: verifying and documenting four scales for addition to
`generate_music_gemini.py`'s scale-generator family
(`get_pentatonic`, `get_dorian`, `get_phrygian`, `get_phrygian_dominant`,
`get_major`, `get_lydian`, `get_natural_minor`, `get_harmonic_minor`,
`get_blues`, `get_whole_tone`, plus the inline `major_pent`/`mixo` branches
in `build_melody()`): **melodic minor (jazz minor)**, **locrian**,
**altered/super-locrian**, and **bebop dominant**.

## Confirming the gap

Grepped every `get_*` scale function and every inline scale branch in
`build_melody()` (the `elif scale == '...':` chain at line ~1411-1440). Full
inventory of what exists: `pent` (minor pentatonic), `dorian`, `phryg`
(phrygian), `phryg_dom` (phrygian dominant — 5th mode of harmonic minor),
`major_pent`, `mixo` (mixolydian, inline), `major` (ionian), `lydian`,
`natural_minor` (aeolian), `harmonic_minor`, `blues`, `whole_tone`. That's
minor pentatonic + all diatonic major-scale modes *except* locrian, plus
harmonic minor and one of its modes (phrygian dominant), plus blues and
whole-tone as outside-the-diatonic-system color scales.

Confirmed absent, no partial/inline equivalent found anywhere in the file:
- **Melodic minor (jazz minor)** — not present. The only "minor with raised
  degrees" scale is `harmonic_minor` (raised 7th only, b6 kept). No raised-6th
  variant exists at all.
- **Locrian** — genuinely the *only* diatonic major-scale mode missing from
  an otherwise complete set (ionian/major, dorian, phrygian, lydian,
  mixolydian/inline, aeolian/natural_minor are all present; locrian is not).
- **Altered / super-locrian** — not present. `phryg_dom` is sometimes
  confused with altered-scale territory (both are "exotic dominant" scales)
  but they are structurally different (phrygian dominant has a *natural* 5th
  and b2/b6; altered has a *diminished* 5th and b9/#9/#11/b13 — see formulas
  below). No overlap in code.
- **Bebop dominant** — not present. No 8-note scale exists anywhere in the
  file; every `get_*` function returns a 5, 6, or 7-note scale. This is a
  structurally new category (chromatic passing-tone scale), not just a new
  interval set.

## Melodic minor (jazz minor)

**Interval formula (semitones from root):** `0, 2, 3, 5, 7, 9, 11`
(W-H-W-W-W-W-H). Identical to the major scale except a minor 3rd. In jazz,
played identically ascending and descending (unlike the classical
melodic-minor convention of a different descending form)
([Wikipedia jazz minor scale](https://en.wikipedia.org/wiki/Jazz_minor_scale),
[jazzguitar.be melodic minor modes](https://www.jazzguitar.be/blog/melodic-minor-modes/)).

**Idiomatic use:** primary color for `m(maj7)`/`m6`/`m9`/`m11`/`m6/9` chords
— i.e. minor chords with a *major* 7th or 6th rather than the flat 7th used
elsewhere in the codebase's `_GUIDE_TONES` table (which only has `(3,10)`
minor-7 and `(4,11)` major-7 pairs — no `(3,11)` minMaj7 entry exists). Also
the source scale for the four most commonly used modal-minor modes: mode II
= Locrian ♮2 (half-diminished ii scale), mode IV = Lydian dominant, mode VII
= altered/super-locrian
([learnjazzstandards 4 applications](https://www.learnjazzstandards.com/blog/4-application-ons-of-the-melodic-minor-scale/)).
Directly implementable as `get_melodic_minor(root)` mirroring the existing
`get_harmonic_minor` structure exactly, just swapping the last interval `11`
in place and also raising the 6th (`8`→`9`).

## Locrian

**Interval formula:** `0, 1, 3, 5, 6, 8, 10` (H-W-W-H-W-W-W). Seventh mode
of the major scale; the only diatonic mode with a diminished 5th, giving it
a built-in half-diminished/diminished-triad quality
([mynewmicrophone locrian](https://mynewmicrophone.com/locrian-mode/),
[learnjazzstandards locrian](https://www.learnjazzstandards.com/blog/locrian-mode/)).

**Idiomatic use:** the textbook scale choice over half-diminished (m7b5)
chords — root-position Locrian's tritone (root to b5) is exactly the
characteristic interval of the m7b5 chord itself
([Wikipedia half-diminished seventh chord](https://en.wikipedia.org/wiki/Half-diminished_seventh_chord)).
This pairs directly with the repo's existing `Bm7b5` chord (used in
progressions #2, #32, #39 as the ii of a minor ii-V-i) — right now the
melody engine has no scale that correctly outlines that chord's color;
`natural_minor` or `pent` are the closest available substitutes but both
contain a perfect 5th where Locrian has a b5, so neither is harmonically
correct against `Bm7b5`. In practice, many jazz players substitute
**Locrian ♮2** (raise the 2nd degree: `0, 2, 3, 5, 6, 8, 10`) over ii of a
minor ii-V-i to soften the harsh b9-against-root clash of pure Locrian's b2
([jazz-guitar-licks Locrian natural 2](https://www.jazz-guitar-licks.com/pages/guitar-scales-modes/modes-of-the-melodic-minor-scale/the-locrian-2-scale-guitar-lesson-with-diagrams.html)) —
worth implementing as a documented alternative/variant of plain Locrian
rather than a fully separate scale table entry.

## Altered scale (super-locrian)

**Interval formula:** `0, 1, 3, 4, 6, 8, 10` (H-W-H-W-W-W-W). Also the 7th
mode of the melodic minor scale (built starting a half-step above a dominant
root) — i.e. every note except the root is flattened relative to major:
b9, #9(=b3 enharmonically), b5(=#11 enharmonically), b13(=#5), b7
([Wikipedia altered scale](https://en.wikipedia.org/wiki/Altered_scale),
[jazz-guitar-licks altered/super locrian](https://www.jazz-guitar-licks.com/pages/guitar-scales-modes/modes-of-the-melodic-minor-scale/the-altered-scale-super-locrian-mode.html)).
Practical construction shortcut confirmed by multiple sources: for a
`C7alt`, play the melodic-minor scale a half-step *above* the dominant root
(Db melodic minor for C7alt)
([learnjazzstandards altered scale](https://www.learnjazzstandards.com/blog/altered-scale-in-solos/)).

**Idiomatic use — directly relevant to the existing codebase:** the altered
scale is *the* standard color over any `7alt`/heavily-altered dominant, and
critically, **the altered scale over a dominant chord is note-for-note
identical to the Lydian dominant scale built on that dominant's tritone
substitute** — e.g. G altered = Db lydian dominant, same seven notes
([jazzadvice altered scale](https://www.jazzadvice.com/lessons/keys-to-the-altered-scale/)).
This means the altered scale is the melodic bridge that makes the repo's
existing `_SEC_DOM_SUBS` tritone-substitution machinery (`G7↔Bb7`, etc.)
melodically coherent — right now a substituted `Bb7` chord has no dedicated
scale in `build_melody()`'s scale list at all (it would fall back to
whatever `scale=` the sub-genre config picked, usually unrelated to the
substituted chord). Adding `get_altered(root)` and wiring it as the melody
scale specifically during bars where `maybe_sub_chord()` has fired closes
that gap directly.

## Bebop dominant

**Interval formula:** `0, 2, 4, 5, 7, 9, 10, 11` (8 notes — Mixolydian with
an added major-7th chromatic passing tone between b7 and the octave root:
2-2-1-2-2-1-1-1 semitone steps)
([muted.io dominant bebop scale](https://muted.io/dominant-bebop-scale/),
[learnjazzstandards bebop scales](https://www.learnjazzstandards.com/blog/learning-jazz/jazz-theory/use-bebop-scales-like-pro/)).

**Idiomatic use:** the added chromatic tone is not decorative — it exists
specifically so that when the 8-note scale is played in continuous eighth
notes starting on a chord tone, the chord tones (root, 3rd, 5th, b7)
land back on the strong beats/downbeats every time, since an 8-note scale
divides evenly into common beat groupings where a 7-note scale doesn't
([Wikipedia bebop scale](https://en.wikipedia.org/wiki/Bebop_scale),
[pdmusic bebop scales guide](https://www.pdmusic.org/bebop-scales/)). This
is a *rhythmic-alignment* device, not a color device like the other three —
its value to the codebase is specifically for dense/fast passages
(`density='dense'` in `build_melody()`, used for climax loops) where
continuous eighth/sixteenth runs currently risk landing chord tones on weak
beats since the existing scales are all 7-note (or fewer). Works over any
plain dominant 7 chord (`G7`, `C7`, `D7`, etc.), including the repo's
existing secondary-dominant substitutes.

## Concrete additions

| table/function to extend | proposed entries | rationale |
|---|---|---|
| new function `get_melodic_minor(root)` | intervals `[0, 2, 3, 5, 7, 9, 11]`, same 3-octave/range-clamp structure as `get_harmonic_minor` (mirror lines 967-975) | fills the "raised 6th+7th minor" gap; needed for `m(maj7)`/`m6` chord-tone melodic support and as the parent scale for locrian-♮2/altered/lydian-dominant modes |
| new function `get_locrian(root)` | intervals `[0, 1, 3, 5, 6, 8, 10]`, same structure | only missing diatonic mode; pairs with existing `Bm7b5` chord in progressions #2, #32, #39 |
| new function `get_locrian_nat2(root)` (variant) | intervals `[0, 2, 3, 5, 6, 8, 10]` | softer alternative to pure Locrian for ii of minor ii-V-i, avoids harsh b9-vs-root clash; optional companion to `get_locrian` |
| new function `get_altered(root)` | intervals `[0, 1, 3, 4, 6, 8, 10]`, same structure | color scale for `7alt`/`7b9`/`7#9` dominants; melodically unifies with existing `_SEC_DOM_SUBS` tritone-sub logic (altered scale ≡ lydian dominant of the tritone-sub root) |
| new function `get_bebop_dominant(root)` | intervals `[0, 2, 4, 5, 7, 9, 10, 11]` (8-note, no octave-range dedup needed but keep existing range clamp) | rhythmic chord-tone-on-downbeat alignment for dense/fast melody passages over any dominant 7 chord |
| `build_melody()` scale branch chain (~line 1411) | add `elif scale == 'melodic_minor': notes_scale = get_melodic_minor(key_root)`, `elif scale == 'locrian': ... get_locrian(key_root)`, `elif scale == 'altered': ... get_altered(key_root)`, `elif scale == 'bebop_dominant': ... get_bebop_dominant(key_root)` | wires the four new functions into the existing dispatch, matching the pattern of every other scale branch |
| `build_melody()` altered-scale auto-select | when `maybe_sub_chord()` has substituted a dominant at the current bar (detectable via `progression`/`prog_bars` lookup), bias scale selection toward `'altered'` for that phrase | closes the melodic gap noted above: substituted dominants currently have no dedicated matching scale |
