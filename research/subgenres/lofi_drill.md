---
subgenre_key: lofi_drill
status: existing
bpm_range: [68, 80]              # current code: (72, 88). Sources describe drill's base groove as sitting at 60-75 BPM (with hi-hats playing double/triple time to create a faster *perceived* tempo of 140-150), and even UK's faster 140-BPM writing convention still reads as a half-time ~70 feel. Recommend lowering the code's band (72-88, which overlaps too much with hip_hop_lofi/study_lofi) toward 68-80 to better encode drill's genuinely slow, half-time-felt base pulse — the "faster" quality should come from hi-hat density/energy setting, not raw BPM.
swing_range: [0.62, 0.72]        # matches current code (0.63, 0.74) closely — sources confirm drill "isn't super quantized like EDM... natural bounce, slightly off-grid hi-hats," with the tresillo-influenced hi-hat pattern being drill's most distinctive swung element. Recommend keeping the current heaviest-swing-tier positioning (already correctly the most swung profile in the roster alongside lofi_phonk) with only a marginal floor adjustment; essentially confirmed.
scales: [phrygian, harmonic_minor, natural_minor, phrygian_dominant]
mood_descriptors: [menacing, tense, gritty, brooding, relentless]
---

## Harmony
Lofi_drill should be the darkest, most harmonically tense profile in the roster: sources on drill/dark-trap chord work specifically cite the Phrygian scale's flat-second interval as "menacing and exotic," and the repetitive bII-i (major-chord-a-semitone-above-tonic to minor tonic) vamp as a defining dark-trap/drill progression device — distinct from lofi_drill's current natural_minor/harmonic_minor/phryg/pent blend by leaning harder into that specific bII-i motion rather than functional jazz turnarounds. Diminished chords (stacked minor thirds) are cited as "the darkest chord in music" and worth using as passing/transition color. Minor keys generally (C/D/E/F/G minor cited as drill defaults) with harmonic minor for extra "aggressive" edge over plain natural minor.

## Melody
Detuned or heavily processed piano/string melody playing simple, repetitive figures is the cited technique for maintaining "a consistent, menacing atmosphere" — favor short, repeated 2-3 note motifs over the code's fuller motif-development arc used elsewhere, since drill's melodic ethos is hypnotic repetition, not song-like development. The code's GM_ORGAN_ROCK melody choice supports a gritty, distorted-adjacent texture well; dissonant, semitone-adjacent melodic movement (echoing the Phrygian b2) reinforces the "eerie" quality sources associate with the genre.

## Rhythm/groove
This is drill's most technically distinctive section: the sliding/gliding 808 bass — pitch-bent, portamento-style movement between notes rather than discrete pitch hits — is called "the single most recognizable production element in modern drill," and should be the loudest differentiator versus lofi_phonk (drill's closest sibling in this codebase) if a bass-slide feature exists or is added. Hi-hats mix straight 16th notes with triplet groupings and irregular, tresillo-influenced off-beat placement — more rhythmically complex/asymmetric than any other subgenre's hi-hat pattern, which supports keeping lofi_drill's current widest/heaviest swing-range positioning and its 'high' energy setting.

## Arrangement/structure
Sparse, ominous arrangement — "avoid overloading the arrangement" is explicit production advice, keeping the 808 slide and hi-hat pattern as the clear rhythmic centerpiece rather than dense layering. Hard-hitting, crisp-snare drums with impactful kicks and "subtle distortion or saturation for that gritty drill character" should inform the drum-pattern/velocity choices — heavier, more aggressive dynamics than any other lofi subgenre, closer to trap production values filtered through a lofi lens.

## Reference repos/algorithms
No dedicated lofi-drill algorithmic generator repos found; closest reference is producer-facing drill tutorial content (808Melo/UK drill lineage feeding into Pop Smoke's Brooklyn-drill crossover) plus commercial sample packs explicitly branded "Lofi Drill" (Samplesound) confirming this as an established micro-genre with its own MIDI/WAV construction-kit convention worth studying for drum-pattern-index calibration. The genre's own defining technical signature (808 pitch-slide) is a production-layer feature outside this codebase's current chord/melody/drum-pattern config scope — worth flagging as a "needs new feature" note for the bass-generation code, not just a scale/swing tuning.

## Provenance
- [Drill Chords: 10 Dark Chord Progressions for Hard-Hitting Tracks | LANDR](https://blog.landr.com/drill-chords/)
- [Trap Chord Progressions for Producers - ChordMap](https://chordmap.io/trap-chord-progressions)
- [What Is Drill Music? Production Guide + History | Amped Studio](https://ampedstudio.com/blog/what-is-drill-music/)
- [How to Make Drill Beats That Are Gritty & Captivating (2025)](https://unison.audio/how-to-make-drill-beats/)
- [The Transatlantic Movement of Drill Music](https://hmc.chartmetric.com/the-transatlantic-movement-of-drill-music/)
- [What Is Drill Music? Sound, BPM, and Regional Styles | Orphiq](https://orphiq.com/resources/what-is-drill-music)
- [Lofi Drill - Lo-Fi Sample Pack (WAV and MIDI Files) – Samplesound](https://www.samplesoundmusic.com/products/lofi-drill)
