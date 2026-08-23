---
subgenre_key: piano_lofi
status: existing
bpm_range: [68, 84]              # current code: (66, 84). Sources on lofi piano specifically (e.g. "slow tempo acoustic piano instrumental solos around 75 BPM," "Lofi Jazz Beat at 80 BPM") cluster tightly around the low-70s-to-low-80s. Recommend nudging the floor up slightly (68 vs 66) — 66 dips a bit close to ambient/lofi_classical's beatless territory, and piano_lofi should retain a felt (if soft) pulse per the Einaudi-style "driving energy" minimalist-pattern technique cited below, distinguishing it from the more static ambient/lofi_classical pair.
swing_range: [0.52, 0.60]        # current code: (0.53, 0.63). Sources emphasize rubato (freely, expressively bending time, especially in intros/outros/solo passages, per Bill Evans/Keith Jarrett convention) as more idiomatic to solo/expressive piano than a heavy backbeat swing feel. Recommend narrowing the band slightly (0.52-0.60 vs 0.53-0.63) to keep piano_lofi closer to a "breathing," rubato-adjacent straight feel than the more overtly grooved cozy_cafe/study_lofi.
scales: [major_pentatonic, pentatonic_minor, dorian, major]
mood_descriptors: [reflective, tender, intimate, unhurried, wistful]
---

## Harmony
Piano_lofi's clearest technical model is Ludovico Einaudi-style minimalism: accessible diatonic progressions (the I-V-vi-IV pop-classical staple and its rotations, e.g. vi-IV-I-V) applied with "the pacing of a classical sonata," including deliberate pauses and silence between phrases rather than continuous jazz-club chord streams. A short repeated harmonic cell (a "drone base" of 3-4 chords) provides stable footing while a melody dances above — this favors the code's shorter, more repetitive progression choices over its denser jazz-turnaround options, distinguishing piano_lofi from the busier jazz-cafe/lofi_jazz harmonic language even though both share extended 7th/9th vocabulary.

## Melody
Melody should be the clear foreground voice (piano solo/lead, not comping under a beat), with an Einaudi-informed technique of a simple repeated cellular motif that "expands into repeated patterns of notes that build and grow" — i.e., the code's motif-development/climax-arc melody engine is a strong structural fit here specifically. Phrase pacing should include "pregnant pauses" — deliberate silence, not just low density — giving piano_lofi a more spacious, breath-taking quality than the steadily-looping study_lofi or the busier vibraphone runs of jazz_cafe/cozy_cafe.

## Rhythm/groove
Timing should favor a soft, felt-piano touch over an assertive drum-driven groove — where percussion exists it should stay minimal and secondary, letting the piano's own rubato-inflected phrasing carry the time-feel. Reduced attack noise / "felt piano" articulation (achieved via the una corda/soft-pedal convention, muting hammer attack for a gentler, rounder tone) is the genre's signature timbral device — closer to Nils Frahm's felt-piano work than to a boom-bap pocket. Where the engine needs a concrete swing value, keep it light and non-insistent (see swing_range above) rather than deliberately funky.

## Arrangement/structure
Sparse arrangement with the piano dominant and other instruments (cello, warm pad) providing only quiet harmonic support underneath — the code's existing GM_CELLO cmelo choice is well-suited to this. Reverb should be spacious ("airy," "spacey reverb added to felt pianos") to give the solo piano a sense of room and distance without becoming ambient's textureless drone. Structurally, favor a clear intro-build-release arc (Einaudi's minimalist "driving energy" through pattern accumulation) over the static loop-and-vamp structure appropriate to ambient or vaporwave.

## Reference repos/algorithms
No dedicated piano-lofi algorithmic-generation repos found; Ludovico Einaudi's catalog (and its well-documented harmonic analysis, e.g. the I-V-vi-IV / vi-IV-I-V pop-classical progression family) is the strongest available "reference corpus" for calibrating both harmony and the minimalist pattern-development technique this codebase's motif/climax-arc melody engine can already approximate. Una Corda-style felt-piano VST/sample libraries (Native Instruments, David Klavins/Nils Frahm collaboration) are the relevant production reference for timbral authenticity, though out of scope for this MIDI-generation engine.

## Provenance
- [Ludovico Einaudi: Minimalism & Pedagogy – PianoMode](https://pianomode.com/explore/piano-inspiration-stories/music-composers/ludovico-einaudi-minimalism-pedagogy/)
- [Best Einaudi songs: 10 works by the minimalist pianist and composer - Classic FM](https://www.classicfm.com/composers/einaudi/ludovico-best-works/)
- [Una Corda – upright piano | Komplete](https://www.native-instruments.com/en/products/komplete/keys/una-corda/)
- [Using felt piano creatively | MusicTech](https://musictech.com/guides/essential-guide/using-felt-piano-creatively/)
- [Tempo Rubato: Enhance Your Musical Expression Like A #1 Pro](https://www.learnjazzstandards.com/blog/tempo-rubato/)
- [How to create a lo-fi piano in Ableton - Blog | Splice](https://splice.com/blog/lo-fi-piano-ableton/)
