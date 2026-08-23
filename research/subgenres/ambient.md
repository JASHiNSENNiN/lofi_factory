---
subgenre_key: ambient
status: existing
bpm_range: [58, 72]              # current code: (58, 74). Sources converge on ambient having no reliable "beat" at all, or when a pulse is present it sits 60-90 (some cite up to 120 for danceable ambient-techno, not relevant here). For this lofi-adjacent ambient profile, keep the code's low end (58) but trim the top from 74 to 72 — ambient's felt tempo should stay well under the "groove-forward" lofi genres like study_lofi or chillhop, reinforcing its beatless/textural identity.
swing_range: [0.50, 0.58]        # current code: (0.50, 0.60). Sources describe ambient as deliberately rejecting 4/4 groove logic (Eno) in favor of rubato/free-time feel; when a pulse exists it should read as nearly metronomic-soft, not swung. Recommend narrowing the top to 0.58 so ambient stays the straightest-feeling profile alongside vaporwave/lofi_classical, not overlapping city_pop's swing.
scales: [pentatonic_minor, natural_minor, whole_tone, dorian]
mood_descriptors: [spacious, weightless, meditative, unresolved, immersive]
---

## Harmony
Ambient treats harmony as texture rather than function: chords change slowly — sometimes once per minute — and voicings favor suspended chords, open fifths, and modal vamps over resolving cadences. Secundal/quartal/quintal (stacked 2nds/4ths) harmony gives a fresher, less "song-like" color than tertian jazz chords. A key technique is deliberately avoiding dominant-7th-type chords that "want" to resolve, so the piece can circle a tonal center indefinitely without forward pull — this favors static pad/drone-holds over the code's existing progression-driven approach, so ambient tracks should pick from the sparsest, slowest-moving progressions available (long note values, minimal chord-per-bar changes) rather than functional turnarounds. A bass drone (single sustained note) under shifting upper-voice color is a strong, easy-to-implement idiomatic device.

## Melody
Melody is minimal-to-absent, or reduced to slow, spaced single-note phrases and gentle arpeggios rather than motif-driven development. Where melody appears, whole-tone or pentatonic fragments float over the pad bed with long note durations and generous rests — density should stay firmly at "sparse," lower than any other subgenre in the roster. Avoid climactic phrase arcs (phi-point buildups) that other subgenres use; ambient melody should feel directionless and contemplative, more a texture layer than a foreground line.

## Rhythm/groove
Largely beatless, or with an extremely soft, buried pulse — no discernible backbeat, minimal-to-no kick/snare urgency, and what percussion exists should sit low in the mix as texture (soft mallet or noise-based hits) rather than groove-anchoring. Where the engine's drum-pattern system requires *some* pattern, favor the sparsest, most skeletal options with heavy velocity reduction. Timing should feel closer to free/rubato than swung — Eno explicitly rejected 4/4 dance-music logic in favor of texture-first composition.

## Arrangement/structure
Generative/evolving rather than sectioned: slow loops, soft attacks, long reverb tails, and sparse events that let a listener drift between passive and active attention (Eno's foundational description). Structure builds through gradual layering and filter automation (slow filter sweeps opening/closing over the whole pad) rather than verse/chorus contrast or drum fills. Reverb should be long-decay and long-pre-delay to create distance and "bloom," and background texture layers (soft noise, vinyl-style hiss, granular drift) should sit around -30 to -24dB to glue the mix without competing with the pad foreground.

## Reference repos/algorithms
Brian Eno's generative-music principles (popularized via SSEYO Koan Pro, one of the first algorithmic music generation systems, 1995) are the closest historical analogue to this codebase's procedural approach — slow probabilistic loops of independent length that phase in and out of alignment. Modern open-source generative-ambient tools worth referencing for technique (not direct reuse) include Sonic Pi's `ambient` example patterns and granular-synthesis libraries (e.g. `librosa`/`pedalboard` reverb chains) for the long-tail reverb effect central to the genre.

## Provenance
- [Ambient Chord Progressions: Pads, Drones + MIDI | ChordGen](https://www.chordgen.org/chords/ambient)
- [How to create a lush ambient chord progression | MusicRadar](https://www.musicradar.com/how-to/create-ambient-chord-progression)
- [Twenty Techniques For Generative Music, Inspired By Brian Eno – Synthtopia](https://www.synthtopia.com/content/2019/04/24/twenty-techniques-for-generative-music-inspired-by-brian-eno/)
- [In the Background: Brian Eno and the Making of Ambient Music – Kadenze Blog](https://blog.kadenze.com/creative-technology/in-the-background-brian-eno-and-the-making-of-ambient-music/)
- [What is Ambient Lofi? - Micro Genre Music](https://microgenremusic.com/genres/ambient/what-is-ambient-lofi/)
- [Stars of the Lid — Wikipedia](https://en.wikipedia.org/wiki/Stars_of_the_Lid)
- [Ambient BPM Range: What BPM Is Ambient? (60-90 BPM)](https://bpmcalc.com/genres/ambient/)
- [Ambient BPM: 60-120, Sweet Spot 90 | Vibes](https://vibesdj.io/dj-tools/what-bpm-is-ambient)
- [The Art of Texture Layering in Lo-Fi Beatmaking](https://lofiweekly.com/2026/03/16/shaping-your-signature-sound-the-art-of-texture-layering-in-lo-fi-beatmaking/)
