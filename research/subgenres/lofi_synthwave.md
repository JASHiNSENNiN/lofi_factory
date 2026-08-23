---
subgenre_key: lofi_synthwave
status: new_candidate
bpm_range: [78, 100]
swing_range: [0.50, 0.58]
scales: [dorian, natural_minor, major, lydian]
mood_descriptors: [nocturnal, cinematic, driving, neon-lit, wistful-retro]
---

## Harmony
Synthwave chord work is described as centered on major/minor 7th chords, suspended chords, and inversions "to achieve that distinctive 80s vibe," with verses/choruses typically built around just 2-3 looping chords that leave space for arpeggios and leads to dominate — a structurally different harmonic role than most of this codebase's roster, where the chord progression itself is usually the main harmonic interest. This makes lofi_synthwave meaningfully distinct from `vaporwave` (which shares 80s nostalgia but is built from slowed/chopped samples with no driving arpeggio engine) — synthwave should keep chords simple and let a continuous arpeggiated line carry harmonic motion instead.

## Melody
The arpeggio is explicitly "the melodic engine of synthwave — a repeating note sequence built from the chord tones of each chord, running continuously as the harmonic backdrop of the entire track," typically an LFO-synced 16th-note or 8th-note-triplet pattern. This is the single clearest mechanical differentiator from every existing subgenre in this codebase, none of which have a dedicated continuous-arpeggio melodic mode (all current melody engines are motif/phrase-based) — implementing lofi_synthwave authentically would need a new arpeggiator melody mode, flagged here as a "needs new melody-generation feature," rather than being achievable by scale/BPM/swing tuning alone.

## Rhythm/groove
Classic synthwave/retrowave production is built on gated-reverb, punchy analog-style drum-machine hits (Simmons-style toms, handclaps, a driving straight-8th or 16th pulse) — a fundamentally different, more electronic-and-propulsive rhythmic character than any boom-bap-descended lofi subgenre in the roster. Swing should stay light-to-minimal (straighter than even `lofi_house`) since synthwave's rhythmic interest comes from the arpeggio's density and the drum machine's tight, quantized precision, not from a human-feel shuffle.

## Arrangement/structure
"Night drive" cinematic pacing — steady, propulsive, often building through added synth layers (pad, arpeggio, lead) over a constant rhythmic bed, evoking 80s action-movie/retro-futurist soundtrack scoring rather than lofi's typical loop-and-vamp economy. This gives lofi_synthwave a clearer forward-motion arrangement identity than `vaporwave`'s static, looped mall-muzak stillness — the two should read as opposite poles of "80s-nostalgia lofi" (vaporwave: slowed/melted/static; lofi_synthwave: driving/propulsive/cinematic) rather than redundant with each other.

## Reference repos/algorithms
No dedicated lofi-synthwave algorithmic-generation repos found in this research pass (web search budget was exhausted before a dedicated artist/production query could be run for this candidate — this profile leans more heavily on established genre knowledge than the other files in this batch and would benefit from a follow-up research pass, particularly on gated-reverb drum-machine production technique and canonical artist reference points such as Kavinsky, Perturbator, and The Midnight). The one search that did complete confirms the core arpeggio-as-harmonic-engine mechanic as the genre's defining, codebase-relevant technical feature.

## Provenance
- [Synthwave Chord Progressions: A Retro Guide - Stay Tuned](https://staytunedguitar.com/synthwave-chord-progressions)
- [5 Synthwave Chord Progressions To Create Dreamy, Retro Tracks](https://unison.audio/synthwave-chord-progressions/)
- [7 Common Synthwave Chord Progressions](https://emastered.com/blog/synthwave-chord-progressions)
- [How to Make Synthwave Music: Production Guide (BPM, Synths, Chords)](https://beatkey.app/how-to-make-synthwave-music)
- [How to make an '80s-style synth track in your DAW | MusicRadar](https://www.musicradar.com/how-to/how-to-make-an-80s-style-synth-track-in-your-daw)
