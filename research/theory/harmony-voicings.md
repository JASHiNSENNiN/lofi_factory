# Harmony & Voicings — Research Notes

Scope: jazz-borrowed harmony for extending `generate_music_gemini.py`'s chord
vocabulary — `PROGRESSIONS`, `VOICING_OPTIONS`, `_GUIDE_TONES`,
`_CHORD_EXTEND_UP`, `_SEC_DOM_SUBS`, `BASS_ROOTS`. Baseline audit of what
already exists is folded into each section so the "Concrete additions" table
at the end is genuinely additive, not redundant.

## What the codebase already has

`VOICING_OPTIONS` (line ~263) covers: m7/m9 (Am7/Am9, Dm7/Dm9, Em7, Gm7/Gm9,
Cm7, Fm7, Bm7b5), maj7/maj9 (Cmaj7/9, Fmaj7/9, Gmaj7, Bbmaj7, Ebmaj7), one
maj7#11 (`Fmaj7s`, Lydian #11), and dominant 7 with a partial altered
extension (`G7b9`, `E7b9`) but no `#9`, `#11`, `13`, or full `alt`. Guide
tones (`_GUIDE_TONES`) encode only the 3rd/7th pair per chord, which is
sufficient for voice-leading logic but says nothing about extensions beyond
the 7th. `_CHORD_EXTEND_UP` is a *tension escalation* table — it doesn't add
new chord qualities, only swaps existing 7th-chord entries for their already
present 9th-family sibling. `_SEC_DOM_SUBS` already implements secondary
dominants (V7/IV, V7/vi, V7/I, V7/ii, V7/iv) and one genuine tritone sub
(G7→Bb7). `PROGRESSIONS` has one explicit minor ii-V-i (`Bm7b5→E7b9→Am7`,
entry #2) and one with a deceptive/tritone-flavored extension (#32, #39).
There is no modal-interchange table, no negative harmony, no quartal/rootless
voicing generation (voicings are hand-written note lists, not derived), and
no neo-soul-specific reharmonization logic (secondary-dominant substitution
is the only "reharm" mechanism present).

## Extended chords (maj7/m7/9/11/13)

Extensions stack in thirds past the 7th: 9th, 11th, 13th are the octave-plus
2nd/4th/6th. On major-quality chords the natural 11th clashes a half-step
against the major 3rd, so jazz voicings almost always raise it to `#11`
(hence `Fmaj7s` in the existing table being the right instinct — it should be
generalized). Minor 9/11 chords don't have that clash (whole step between
b3 and 11), so `m11` is usable un-raised, unlike `maj11`
([PianoGroove chord extensions](https://www.pianogroove.com/jazz-piano-lessons/chord-extensions-9ths-11ths-13ths/),
[Jazz Tutorial chord symbols](https://jazztutorial.com/articles/jazz-chord-symbols-explained)).
Dominant chords support the widest alteration palette: `7b9`, `7#9`, `7#11`,
`13`, and the "kitchen sink" `7alt` (`b9,#9,b13,#11` simultaneously) used
constantly in neo-soul turnarounds. The repo already has `G7b9`/`E7b9`;
`13`/`#9`/`#11` dominant variants and `m11`/`m6`/`maj6` are the clean gaps.

## ii-V-I and variants

Standard major ii-V-I: `Dm7 - G7 - Cmaj7`. Variants worth encoding
explicitly: **back-cycled** turnarounds (`vi-ii-V-I`, e.g. `Am7-Dm7-G7-Cmaj7`
— the repo's #28 `Cmaj7-Am9-Dm9-G7` is a related but different ordering:
I-vi-ii-V), **extended-dominant** V substitutions (G7→G13/G7#11/G7alt, purely
a voicing swap, no new progression entries needed), and **minor ii-V-i**
(`Dm7b5 - G7alt - Cm` / in the repo's existing key: `Bm7b5 - E7b9 - Am7` is
exactly this pattern already, just needs siblings in other keys — Gm context
would be `Am7b5 - D7b9 - Gm7`, Fm context `Gm7b5 - C7b9 - Fm7`)
([Learn Jazz Standards ii-V-i](https://www.learnjazzstandards.com/blog/ii-v-i-with-tritone-sub-chord-progression-workout/),
[Wikipedia ii–V–I](https://en.wikipedia.org/wiki/Ii%E2%80%93V%E2%80%93I_progression),
[thejazzpianosite II-V substitution](https://www.thejazzpianosite.com/jazz-piano-lessons/jazz-reharmonization/ii-v-substitution/)).

## Secondary dominants & tritone substitution

A secondary dominant is a V7 (or V7-derived chord) that resolves to
something other than the tonic — "the dominant of a non-tonic chord," e.g.
`A7 → Dm7` is V7/ii ([My Music Theory](https://mymusictheory.com/harmony/secondary-dominants/),
[LearnJazzStandards secondary dominants](https://www.learnjazzstandards.com/blog/secondary-dominants/)).
`_SEC_DOM_SUBS` already covers V7/IV, V7/vi, V7/I, V7/ii, V7/iv in the keys
the progressions use. Tritone substitution replaces a dominant with the
dominant a tritone away — they share the same 3rd/7th tritone (enharmonically
swapped), so the substitution preserves voice-leading tension while creating
chromatic bass motion (`Dm7-Db7-Cmaj7` instead of `Dm7-G7-Cmaj7`)
([learnjazzstandards tritone sub types](https://www.learnjazzstandards.com/blog/learning-jazz/jazz-theory/tritone-substitution-types/),
[Wikipedia tritone substitution](https://en.wikipedia.org/wiki/Tritone_substitution)).
The repo has exactly one true tritone sub (`G7↔Bb7`); the rest of
`_SEC_DOM_SUBS` are secondary dominants, not tritone subs — worth
distinguishing in code comments even without new entries. Missing tritone
subs: Db7 for G7 (only Bb7 present — Bb7 is *also* legitimately Eb's V7, so
it's overloaded; Db7 would be the "purer" unambiguous tritone sub target),
Ab7 for D7, E7 for Bb7.

## Modal interchange / borrowed chords

Borrowing from the parallel minor into a major-key progression: the four
workhorse borrowed chords are **iv** (minor iv instead of major IV — sadder),
**bVI**, **bVII**, and **bIII**
([composerdeck modal interchange](https://composerdeck.com/modal-interchange.html)).
In C major: `Fm` (iv), `Abmaj7` (bVI), `Bbmaj7` (bVII), `Ebmaj7` (bIII). The
repo's C-major progressions (#16-25, #28, #46 etc.) never borrow — every
chord in a "C" `PROGRESSION_KEY` entry is diatonic. This is the single
highest-value, lowest-risk addition: dropping `Abmaj7`→`Am9`-ish substitution
or `bVII` cadences (`Bbmaj7 → Cmaj9`) into 2-3 existing C-major progressions
would add real harmonic color without touching the generation engine's
structure, since these are just new `VOICING_OPTIONS`/`BASS_ROOTS` entries
plugged into new `PROGRESSIONS` rows. Usage pattern: iv as a sadder plagal
substitute for IV, bVI as "a dramatic lift after the V," bVII as a
rock/folk-flavored non-classical resolution back to I
([composerdeck](https://composerdeck.com/modal-interchange.html),
[fachords modal interchanges](https://www.fachords.com/modal-interchanges/)).

## Negative harmony (basics)

Negative harmony reflects every note/chord across an axis at the midpoint
between tonic and dominant (in C: the axis sits between E♭/E, so C↔G,
Dm↔Bb, F↔... reflect pairwise around that axis)
([Wikipedia negative harmony](https://en.wikipedia.org/wiki/Negative_harmony),
[Hello Music Theory](https://hellomusictheory.com/learn/negative-harmony/)).
Traces to Ernst Levy's polarity theory, popularized recently by Jacob
Collier. Practical use here would be generative, not vocabulary: a
`negative_harmony(chord_name, key_root)` transform that maps an existing
diatonic chord to its axis-reflection, giving "alternate universe" versions
of the current `PROGRESSIONS` entries for free. This is architecturally
different from the other additions (a function, not a table), so it's noted
here as a stretch goal rather than a table entry — the payoff (doubling
effective progression variety from the *existing* 51 progressions) is high
but it requires a semitone-mapping helper, not just new dict entries.

## Rootless / drop-2 / spread voicings

Rootless voicings drop the root (bassist covers it) and voice 3-7-9-(5 or
13) instead — "Bill Evans voicings," standard for smooth ii-V-I voice
leading in the piano's mid register
([PianoGroove rootless voicings](https://www.pianogroove.com/jazz-piano-lessons/rootless-chord-voicings/)).
Drop-2 takes a close-position 4-note chord and drops the second-highest
voice an octave, producing the wide horn-section-style spacing common in
comping ([FreeJazzLessons drop 2](https://www.freejazzlessons.com/drop-2-voicings/)).
The repo's `VOICING_OPTIONS` are already hand-voiced rootless-style in
places (e.g. `Am9`'s `[60,64,67,71]` omits the 57-root) but this is
incidental, not systematic — there's no drop-2 spread variant for any chord
(all voicings are compact, span roughly an octave). Adding 1-2 wide
drop-2-style spread voicings per existing chord entry (root moved down an
octave, everything else kept) would add register variety without any new
harmonic vocabulary.

## Quartal voicings (bonus finding, not explicitly requested but directly relevant)

Quartal chords stack perfect 4ths instead of 3rds (`C-F-Bb-Eb`), sound
open/ambiguous with no strong tonal pull, and are a defining texture of
McCoy Tyner/So What–style modal jazz *and* neo-soul/R&B — used especially for
intros, transitions, and "delaying harmonic definition"
([learnjazzstandards quartal harmony](https://www.learnjazzstandards.com/blog/quartal-harmony/),
[Orange Candy neo-soul chords](https://orangecandymusic.com/top-neo-soul-chords-you-need-to-know-and-how-to-use-them/)).
Given the repo already targets a `nujabes`/`neo-soul` sub-genre flavor
(`_SUBGENRE_CONFIG`), a couple of quartal voicings on `Dm7`/`Am7`/`Gm7`
(minor chords voice quartally most naturally) would be a cheap, idiomatically
correct addition.

## Neo-soul reharmonization

Neo-soul harmony leans on secondary dominants, tritone subs, and passing
chords stacked densely, plus "dissonant" voicings like `13b9` and quartal
color tones layered over otherwise simple changes
([jazzpianoconcepts neo-soul tricks](https://www.jazzpianoconcepts.com/post/6-harmonic-tricks-voicings-for-neo-soul-rnb-piano-tutorial),
[drumloopai neo-soul progressions](https://www.drumloopai.com/blog/neo-soul-chord-progressions/)).
The repo's neo-soul progressions (#10, #11, #27, #38) are already close to
this in chord choice (`Am7-G7-Fmaj7-E7b9`, quarter-note turns) — the gap is
in voicing density (no `13`, no stacked quartal color) and passing-chord
insertion between existing chords rather than only chord-to-chord
substitution.

## Concrete additions

| table/function to extend | proposed entries | rationale |
|---|---|---|
| `VOICING_OPTIONS` + `BASS_ROOTS` + `_GUIDE_TONES` | `G13`: `[[55,59,62,64,69],[59,62,64,69,71]]`, root 43, guide `(4,10)` | dominant 13 variant of existing G7, cheap tension option for `_CHORD_EXTEND_UP` |
| `VOICING_OPTIONS` + `BASS_ROOTS` + `_GUIDE_TONES` | `G7alt`: `[[55,59,63,66],[59,63,66,68]]` (b9,#9,b5,b7 compressed voicing), root 43, guide `(4,10)` | fills the missing full-altered-dominant gap; pairs with new altered-scale melodic vocabulary (see scales-modes-gaps.md) |
| `VOICING_OPTIONS` + `BASS_ROOTS` + `_GUIDE_TONES` | `Am11`: `[[57,60,64,67,72],[60,64,67,72,74]]`, root 45, guide `(3,10)`; `Dm11`: `[[50,53,57,60,65]]`, root 38 | minor 11ths are consonant (no #11 needed on minor), currently absent entirely |
| `VOICING_OPTIONS` + `BASS_ROOTS` + `_GUIDE_TONES` | `Am6`: `[[57,60,64,66],[60,64,66,69]]`, root 45, guide `(3,9)`-style (6th not 7th); `Cmaj6`: `[[60,64,67,69]]`, root 48 | 6th chords are a distinct lofi/neo-soul color (softer than maj7/m7, common Rhodes voicing) not present at all |
| `_SEC_DOM_SUBS` | add `'G7': ('Db7', 0.06)` as a second, purer tritone-sub option alongside the existing `Bb7` entry (pick randomly between the two) | current `Bb7` target is overloaded (also functions as Eb's diatonic V7), so a dedicated Db7 target disambiguates true tritone-sub usage |
| `PROGRESSIONS` (new entries) | `[('Cmaj9',2),('Ebmaj7',1),('Fm7',1),('Cmaj9',2),('Bbmaj7',2)]` — I, bIII, iv, I, bVII in C | canonical modal-interchange cadence using the four workhorse borrowed chords, currently absent from every C-major progression |
| `PROGRESSIONS` (new entries) | minor ii-V-i sibling: `[('Am7b5',1),('D7b9',1),('Gm7',2)]` (needs new `Am7b5`, `D7b9` voicing/bass/guide entries, root 57 and 38 dim7-ish resolution to Gm) | repo has only one minor ii-V-i (`Bm7b5-E7b9-Am7`, #2); a second instance in a different key generalizes the pattern rather than leaving it a one-off |
| `VOICING_OPTIONS` | quartal `Dm7q`: `[[50,55,60,65]]` (4ths stack: D-G-C-F over Dm7 bass), `Am7q`: `[[57,62,67,72]]` | idiomatic neo-soul/modal texture completely absent from current third-stacked voicings; use as an alternate voicing choice in `VOICING_OPTIONS['Dm7']`/`['Am7']` rather than a new chord symbol |
