---
subgenre_key: dark_lofi
status: existing
bpm_range: [66, 88]              # code currently uses (65, 80), close. General lofi-hip-hop tempo research puts a "dark"/slower lofi anchor around 60-90 with the common 80-85 midpoint; current range's floor is well-placed but the ceiling (80) could rise slightly toward 85-88 to allow for boom-bap-adjacent darker tracks without losing the genre's inherently slow, heavy character.
swing_range: [0.61, 0.71]        # code currently uses (0.62, 0.71), essentially identical — "heaviest laid-back pocket" per the existing code comment is well-supported; dark/horrorcore-adjacent hip-hop tracks favor a dragging, heavy swing consistent with this.
scales: [phryg, natural_minor, harmonic_minor, blues, pent]
mood_descriptors: [ominous, haunting, unsettling, brooding, cinematic]
---

## Harmony
Phrygian mode is the genre's defining harmonic signature — the flat-2nd scale degree sitting a single semitone above the tonic reads as immediately "menacing and exotic," and Phrygian is described as the second-darkest Western mode after Locrian. The signature move is the bII-i cadence (the "Phrygian Fall": i-bIII-bII-bVI), a half-step descent from the flattened second down to the minor tonic that produces one of the tensest cadences available — this pairs directly with the code's existing 'phryg' scale entry and should be the primary harmonic device, more so than plain natural/harmonic minor. Diminished and half-diminished chords, plus slow chromatic descending bass lines, layer in additional horror-score-style dissonance; augmented chords and the tritone interval appear as color/tension devices in the most extreme (horrorcore-leaning) tracks.

## Melody
Detuned, slightly-out-of-tune instrument character is a deliberate production choice, not a flaw — "dark & detuned" piano/bell patches with haunting, dissonant characteristics, unstable pitch, short sustain, and eerie decay. Melodic phrasing should be sparse and haunting: single sustained tones, occasional bent/detuned notes, wide silences — closer to horror-film scoring gestures than to a "song" melody. Bells (detuned), creaking piano, and muted, filtered guitar/organ leads (matching the existing GM_GUITAR_JAZZ melody choice) fit this palette well if pushed toward dissonance rather than warmth.

## Rhythm/groove
Heavy, dragging swing (the heaviest in the set alongside lofi_phonk and lofi_drill) — the "laid-back pocket" should feel oppressive rather than relaxed. Production techniques include heavy distortion, deep reverb tails that obscure the original sample source, bass drones beneath the mix, and time-stretching for unsettling texture. Compared to lofi_phonk (which adds cowbell-driven Memphis-rap syncopation), dark_lofi is slower and more ambient/drone-adjacent in its low end.

## Arrangement/structure
Atmosphere-first structure — long, evolving drone/pad layers under a sparse beat, minimal melodic "hook" repetition, more akin to dark-ambient scene-setting than a loop-and-vary hip-hop structure. Layering order: bass drone/sub-bass foundation, then sparse detuned chords, then minimal percussion, then occasional dissonant melodic fragments (bell, piano) as punctuation rather than a continuous lead.

## Reference repos/algorithms
None specific — general dark-ambient/horror-scoring production guides (This Is Darkness, UJAM Halloween tutorial) rather than a codified generative model.

## Provenance
- [5 Dark Chord Progressions To Make Your Tracks Haunting & Eerie — Unison Audio](https://unison.audio/dark-chord-progressions/)
- [Crafting Darker Songs with the Phrygian Mode — Audiospring Music](https://audiospringmusic.com/crafting-darker-songs-with-the-phrygian-mode/)
- [Dark Chord Progressions Guide — Motifkit](https://motifkit.com/dark-chord-progressions/)
- [How to Write Dark Chord Progressions — Musiversal](https://musiversal.com/blog/learn-dark-chord-progressions)
- [Dark Ambient 101: Drones — This Is Darkness](https://www.thisisdarkness.com/2018/04/07/dark-ambient-101-drones/)
- [Dark ambient — Wikipedia](https://en.wikipedia.org/wiki/Dark_ambient)
- [How to Make Dark and Ambient Records - Halloween Edition — UJAM](https://www.ujam.com/tutorials/how-to-make-dark-and-ambient-records-halloween-edition/)
- [Dark & Edgy - Detuned Piano — Sample Focus](https://samplefocus.com/samples/dark-edgy-detuned-piano)
- [Fractured Keys — Melancholic Piano Ambient Loops — nativica.itch.io](https://nativica.itch.io/fractured-keys)
- [From Horrorcore To Heartbreak — Hip Hop Golden Age](https://hiphopgoldenage.com/list/from-horrorcore-to-heartbreak-100-dark-dense-and-disturbing-hip-hop-albums/)
- [What Is the Tempo of the Lo-Fi Beat? — drumloopai.com](https://www.drumloopai.com/lofi/what-is-the-tempo-of-the-lofi-beat/)
