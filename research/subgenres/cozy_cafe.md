---
subgenre_key: cozy_cafe
status: existing
bpm_range: [76, 92]              # matches current code (76, 92) — sources on "cafe lounge" tempo (70-100) and lofi-cafe-specific examples (~82 BPM) confirm this band is well-placed; no change recommended.
swing_range: [0.58, 0.66]        # matches current code (0.58, 0.66) — sources cite ~10-20% swing quantization as the "authentic lofi" feel, which maps comfortably into this range; confirmed, no change.
scales: [major_pentatonic, pentatonic_minor, dorian, major]
mood_descriptors: [warm, inviting, intimate, comforting, unhurried]
---

## Harmony
Cozy café is the most straightforwardly "warm jazz" of the bright/cozy cluster: maj7 and 9th chords over a major-key I-vi-IV-V-ish skeleton (e.g., Cmaj7-Am7-Fmaj7-G7), with the classic ii-V-I turnaround (Dm7-G7-Cmaj7) as the resolving cadence of choice — "gentle tension, pull toward home, soft glow." Minor 7ths appear for a touch of mellow melancholy inside an otherwise major-key frame, never full minor-key darkness. Chords should be held long and slow-moving (jazzy but unhurried) rather than busy — this matches the code's existing progression pool (22, 21, 16, 17, 25, 28, 44, 45, 46) which already leans on bright/cadential progressions.

## Melody
Melody sits on warm electric piano (Rhodes/EP2) or vibraphone, played legato with a relaxed, conversational phrasing rather than virtuosic runs — think a musician noodling quietly in the corner of a coffee shop. Major pentatonic and dorian color dominate; occasional blue-note dips add character without pulling into minor-key moodiness. Phrases should be short and call-and-response-like, leaving room for the "café chatter" ambient layer conceptually implied by the genre even though this codebase doesn't render field-recording textures.

## Rhythm/groove
Subtle swung drums with off-grid timing is explicitly cited as a defining lofi-cafe trait — roughly 10-20% swing quantization, brushed or muted hi-hats, walking-adjacent bass movement under a soft boom-bap-lite kick/snare pattern. Groove should feel relaxed and unhurried, never aggressive or syncopated in a "trap" sense (contrast with lofi_drill); the current 0.58-0.66 swing band captures this well.

## Arrangement/structure
Loop-based with gentle variation — steady tempo, minimal dramatic dynamic swings, occasional light fills at section boundaries rather than hard drops. Vinyl crackle and tape-hiss noise-floor (implied/simulated via the engine's humanization/velocity variance) plus soft reverb on the Rhodes gives the "sitting in a rain-dappled window seat" quality repeatedly cited across cafe-lofi playlist descriptions. Warmth comes from tape-saturation-style harmonic coloring rather than pristine digital clarity — the engine's existing soundfont rotation (favoring MuseScore/GeneralUser over harsh GM defaults) already leans this direction.

## Reference repos/algorithms
No dedicated cozy-cafe generator repos found; this is best treated as a mood variant of the broader "lofi hip-hop beat generator" family (chord-loop MIDI + tape/vinyl FX chain scripts common on GitHub, e.g. "lofi-beat-generator" style projects using Rhodes samples + swung MIDI drums). The genre's own defining "generator" is the Lofi Girl livestream aesthetic itself — curated playlists rather than an algorithmic tradition — so procedural fidelity here is best judged against playlist convention (Spotify/YouTube "cozy cafe lofi" curation) rather than a specific artist catalog.

## Provenance
- [LoFi Chord Progressions: The 6 Best Chord Progressions for LoFi Music](https://unison.audio/lofi-chord-progressions/)
- [Cozy LoFi for Winter: 7 Jazzy Holiday Progressions, Rhodes Tricks, and Dusty Textures – LoFi Weekly](https://lofiweekly.com/2026/01/05/cozy-lo-fi-for-winter-7-jazzy-holiday-progressions-rhodes-tricks-and-dusty-textures/)
- [The Ultimate Guide to LoFi Hip-Hop Production](https://audioplugin.deals/blog/the-ultimate-guide-to-lofi-hip-hop-production/)
- [How to Produce Lofi Music: 11 Key Techniques for Vintage Warmth and Smooth Vibes](https://www.merotips.com/2024/11/how-to-produce-lofi-music-11-key.html)
- [Lofi hip-hop — Wikipedia](https://en.wikipedia.org/wiki/Lofi_hip-hop)
- [Making LoFi Beats 101: Create Super Chill, Authentic Tracks](https://unison.audio/making-lofi-beats/)
- [Lofi Tempo: Finding the Perfect Pace for Your Tracks – Mystic Alankar](https://mysticalankar.com/blogs/blog/lofi-tempo-finding-the-perfect-pace-for-your-tracks)
