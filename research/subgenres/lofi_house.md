---
subgenre_key: lofi_house
status: existing
bpm_range: [110, 128]              # code currently uses (88, 100) with energy 'medium'. THIS IS THE BIGGEST DISCREPANCY FOUND: the actual "lofi house" genre pioneered by Mall Grab/DJ Boring/Ross From Friends/DJ Seinfeld runs at ~115-126 BPM (house's standard 115-130 tempo, e.g. one tracked example was 119 BPM), NOT the 70-90 lofi-hip-hop tempo range. The current code's (88,100) reads more like a slow/deep house or a lofi-hip-hop-with-house-chords hybrid than the real internet-genre "lofi house." Recommend raising substantially toward 110-128, or if the intent was deliberately a slower lofi/house hybrid, rename/document that divergence explicitly.
swing_range: [0.52, 0.62]        # code currently uses (0.54, 0.61), close. Real house swing comes from a swung 16th-note hi-hat shuffle (offbeat 16ths dragging late) layered onto an otherwise four-on-the-floor grid — current range is plausible but genuinely straighter (deep house is "mostly straight" per the existing code comment, consistent with research).
scales: [dorian, pent, major]
mood_descriptors: [hypnotic, warped, nostalgic, hazy, danceable]
---

## Harmony
Chord-led rather than melody-led: deep-house-style jazz-influenced minor7/major7 chord stabs (the trademark deep-house harmonic signature) looped and filtered. Common progressions echo lofi's ii-V-I / I-vi-ii-V but with far less movement — a single chord loop (2-4 chords) repeated for the whole track, since the four-on-the-floor pulse and stab rhythm carry the momentum rather than harmonic development. Chord stabs are often warped/detuned samples rather than cleanly played chords — pitch instability is a deliberate aesthetic choice, not an error.

## Melody
Minimal to absent distinct "melody" in the traditional sense — the lead role is often filled by a chopped vocal sample or a repeating chord-stab hook rather than a played line. Where a melodic lead exists (vibraphone per the current config), it functions more as a repeating hook/riff than a developing phrase, mirroring the chord-stab's loop logic.

## Rhythm/groove
Four-on-the-floor kick (quarter notes) is the non-negotiable foundation — this is what most distinguishes lofi_house from every other subgenre in this set, none of which use a four-on-the-floor pattern. Hi-hats sit on the off-8ths/16ths between kicks; deep-house-style shuffle swings the 16th-note hats specifically (dragging the off-16ths late) for a "lazy, half-asleep pocket" while the kick itself often stays straight. A backbeat clap/snare on 2 and 4 layers on top. The "lofi" element is textural: muffled drums, fuzzy synths, a gauzy/saturated "fourth-generation cassette copy" quality via tape/bitcrush processing on drum machine hits.

## Arrangement/structure
DJ-tool-influenced structure: longer, more repetitive builds than hip-hop-lofi tracks, with elements (percussion layers, a filtered chord stab, a vocal chop) introduced and removed gradually rather than through verse/chorus contrast — arrangement changes are additive/subtractive (add a hat layer, drop the bass for 8 bars) to serve continuous dancefloor motion.

## Reference repos/algorithms
None specific — inherits general house-music drum-programming tutorials (four-on-the-floor construction, hi-hat shuffle patterns) rather than a codified generative model.

## Provenance
- [Deep House Chords — Attack Magazine](https://www.attackmagazine.com/technique/passing-notes/passing-notes-deep-house-chords/)
- [The Art of Harmony: Deep House Chord Progressions — Stealify Sounds](https://stealifysounds.com/blogs/news/the-art-of-harmony-exploring-deep-house-chord-progressions)
- [House Drum Patterns: Step-by-Step Beat Making Guide — Amped Studio](https://ampedstudio.com/blog/how-tomake-a-house-beat/)
- [How to program 6 different four-to-the-floor grooves — MusicRadar](https://www.musicradar.com/how-to/how-to-program-6-different-four-to-the-floor-grooves)
- [Beat Dissected: Rolling Deep House — Attack Magazine](https://www.attackmagazine.com/technique/beat-dissected/rolling-deep-house/)
- [Lo-Fi House — Rate Your Music](https://rateyourmusic.com/genre/lo-fi-house/)
- [2016: Lo-fi house emerged from the underground — Mixmag](https://mixmag.net/feature/2016-lo-fi-house-emerged-from-the-underground)
- [Irony Is A Dead Scene: A User's Guide To Lo-Fi House — HighClouds](https://highclouds.org/irony-is-a-dead-scene-a-users-guide-to-lo-fi-house/)
- [BPM and key for songs by Lofi House — SongBPM](https://songbpm.com/@lofi-house)
- [House music — Wikipedia](https://en.wikipedia.org/wiki/House_music)
- [Lo-Fi House Sounds — Loopmasters](https://www.loopmasters.com/genres/174-Lo-Fi-House/products/7164-Essential-Lo-Fi-House)
