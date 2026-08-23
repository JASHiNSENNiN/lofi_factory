---
subgenre_key: vaporwave
status: existing
bpm_range: [60, 80]              # current code: (58, 74). Research (SongBPM/Tunebat aggregate, production guides) puts "classic" vaporwave at 60-80 BPM; code's 58-74 is close but slightly low on the top end — recommend nudging to 60-80 to better cover the mall-muzak/"floral shoppe" core tempo without drifting into ambient/drone territory (<58).
swing_range: [0.50, 0.58]        # current code: (0.50, 0.60). Sources describe vaporwave as built from pitch/time-stretched source material (chopped-and-screwed, slowed 20-40%), which is mechanically straight-grid, not swung. Recommend tightening the top slightly (0.58 not 0.60) to keep it closer to true "warped-tape-straight" than the current range's slight overlap with lofi_house's swing feel.
scales: [lydian, major, dorian, whole_tone]
mood_descriptors: [nostalgic, melancholic, hazy, uncanny, dislocated]
---

## Harmony
Vaporwave's harmonic vocabulary is inherited wholesale from the smooth-jazz, city pop, and elevator-music source material it samples/pastiches: extended jazz chords (maj7, m7, 9ths, 6/9) and ii-V-I or I-IV-V motion, but stretched, slowed, and often left harmonically static for long stretches rather than functionally resolved. A common device is borrowing chords from the parallel minor (e.g., in C major, dropping in an Fm or Ab) for a sudden bittersweet color shift mid-loop — this fits well with the code's existing lydian/major/whole_tone scale pool. Because the genre is loop-based (2-4 bar vamps repeated, not "progressed"), harmonic rhythm should be slow: hold a chord for a full bar or two rather than changing every beat. Open, spread voicings (wide intervals, low bass note separated from upper chord tones) read as more "vaporwave" than close jazz-club voicings.

## Melody
Melody is sparse and secondary to texture — often just a fragment of the sampled source looped and pitched down, or a slow, held synth-pad line with long sustains rather than active phrase-based melody. When present, melodic movement favors stepwise motion within lydian/major color (raised 4th for that "floating," slightly unresolved brightness) or whole-tone runs for a dreamlike, tonally ambiguous blur. Avoid busy 16th-note runs; phrases should breathe with generous rests, mimicking a tape loop that occasionally stutters or repeats a motif verbatim (a chopped-and-screwed "stutter repeat" of 1-2 notes is idiomatic).

## Rhythm/groove
Grooves are minimal and mechanically straight, not swung — a soft, muted kick/snare pattern with lots of space, sometimes barely present at all (many classic vaporwave tracks are near-beatless). Where drums exist, think slow boom-bap or a simple 4-on-the-floor at low velocity, heavily reverbed and low-passed. Tempo itself is a production technique: source tracks are literally slowed 20-40% from their original tempo, which is why the target BPM band (60-80) sits so low. Chopped-and-screwed edits (stutter-cuts, reversed fragments, pitch-bent "record slowing down" effects) are a signature rhythmic/production gesture worth emulating via humanized timing jitter and occasional repeat-note glitches rather than swing per se.

## Arrangement/structure
Loop-driven rather than verse/chorus: a short (often 2-4 bar) sample or motif repeats with minimal variation for the track's duration, sometimes with a pitch-bend "tape stop" ending. Arrangement builds through added layers (a pad swell, a new texture) rather than harmonic development. Wide use of reverb/delay throws and heavy low-pass filtering create the "underwater," distant quality. Silence and negative space matter — a vaporwave arrangement that's constantly full-density loses the genre's dislocated, empty-mall atmosphere.

## Reference repos/algorithms
No dedicated vaporwave-generation GitHub repos found; closest algorithmic analogues are generic "lofi hip hop generator" projects (chord-loop + tape-warble effect chains) and time-stretch/pitch-shift DSP libraries (e.g. rubberband, librosa `effects.time_stretch`) used for the slow-down/pitch-down effect. For programmatic humanization, applying a slow LFO to swing/timing (simulating tape wow-and-flutter) is a more faithful analogue than genre-authentic MIDI swing tables.

## Provenance
- [How to Make Vaporwave: Tools, Samples & Sound (2026 Guide)](https://futureproofmusicschool.com/blog/techniques-for-how-to-make-vaporwave-music-with-authentic-style)
- [Vaporwave — Wikipedia](https://en.wikipedia.org/wiki/Vaporwave)
- [Chopped and screwed — Wikipedia](https://en.wikipedia.org/wiki/Chopped_and_screwed)
- [Top 20 Vaporwave Artists and Bands - MusicalHow](https://www.musicalhow.com/best-vaporwave-artists-and-bands/)
- [2814 — Wikipedia](https://en.wikipedia.org/wiki/2814)
- [Evaporate Together: History of Vaporwave | Perfect Circuit](https://www.perfectcircuit.com/signal/vaporwave-history)
- [BPM and key for songs by Vaporwave | SongBPM](https://songbpm.com/@vaporwave)
- [Mastering Vaporwave: Techniques To Create The Iconic Retro-Futuristic Sound | SoundCy](https://soundcy.com/article/how-to-sound-like-vaporwave)
- [Vaporwave | Aesthetics Wiki | Fandom](https://aesthetics.fandom.com/wiki/Vaporwave)
