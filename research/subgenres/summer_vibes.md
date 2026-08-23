---
subgenre_key: summer_vibes
status: existing
bpm_range: [80, 94]              # matches current code (80, 94) — sits appropriately between chill lofi-beach content (mellow, slow-to-moderate) and full tropical house (100-115, too dance-oriented for this lofi engine); confirmed, no change needed.
swing_range: [0.59, 0.66]        # matches current code (0.59, 0.66) — general lofi swing convention plus "nudging marimba/guitar hits early or late for human push and pull" cited for tropical-adjacent production supports a light-to-moderate swing feel; confirmed.
scales: [major_pentatonic, pentatonic_minor, major]
mood_descriptors: [breezy, carefree, sun-warmed, playful, buoyant]
---

## Harmony
Tropical-house-adjacent sources emphasize major-key progressions for the "escapism, relaxation, carefree enjoyment" mood — brighter and simpler than jazz-cafe extended harmony, favoring clear I-IV-V-vi movement over dense ii-V-I jazz turnarounds. The code's existing progression pool (22, 21, 23, 16, 18, 44, 45, 46, 48) already leans bright/major, which aligns well; keep chord extensions light (add9, maj7 rather than stacked 9th/11th/13th jazz voicings) so the harmony reads as sunny and uncomplicated rather than sophisticated-lounge (contrast with city_pop or jazz_cafe).

## Melody
Mallet percussion (marimba, steel-drum-adjacent timbre) is the definitive melodic voice — sources repeatedly pair "chill lofi marimba" with ocean/beach imagery, and tropical house cites marimba/pan-flute/steel-drum as core tonal color. The code's marimba (`GM_MARIMBA`) as cmelo texture is well-chosen; melody itself (vibraphone) should favor bouncy, syncopated-but-not-busy pentatonic phrases with a playful, dancing contour — more rhythmically active and "bright-percussive" than the legato, held-note phrasing of cozy_cafe or morning_lofi.

## Rhythm/groove
Groove should feel buoyant and forward-moving relative to the rest of the bright/cozy cluster — closer to a chill four-on-the-floor pulse feel (without going full tropical-house EDM tempo/energy) than to boom-bap laid-back-ness. Light swing with humanized micro-timing ("nudging a few milliseconds early/late") gives the mallet hits a natural, sun-drenched bounce rather than a quantized/robotic feel.

## Arrangement/structure
Arrangement should stay light and airy — fewer dense chord stacks, more space between hits, letting mallet timbre and light percussion carry the "beach afternoon" atmosphere. Source material on tropical house's "emotional soft landing" (chords/textures providing gentle release) suggests summer_vibes benefits from brighter dynamic lifts at section boundaries (a marimba flourish or vibraphone run) rather than the more subdued, static arrangement approach of ambient or piano_lofi.

## Reference repos/algorithms
No dedicated summer-lofi generator repos found; closest analogues are generic tropical-house production tutorials (chord-loop plus mallet-sample layering) and the broader curated-playlist tradition ("Wander World Music," "Chill Lofi Marimba & Ocean Waves" YouTube channels) rather than an algorithmic lineage. Treat as a mallet-forward, major-key brightness variant within this codebase's existing "cozy/bright" cluster (alongside cozy_cafe, morning_lofi, anime_lofi, bedroom_pop, city_pop) rather than a wholesale new engine feature.

## Provenance
- [How to make a tropical house track that takes the beach vibe to the dancefloor | Native Instruments Blog](https://blog.native-instruments.com/tropical-house/)
- [Tropical House Summer Melodies | Echo Sound Works](https://www.echosoundworks.com/tropical-house-summer-melodies)
- [Chillwave — Wikipedia](https://en.wikipedia.org/wiki/Chillwave)
- [Chill Lofi Marimba & Ocean Waves — YouTube](https://www.youtube.com/watch?v=sMQDxW_IPd8)
- [LoFi Chord Progressions: The 6 Best Chord Progressions for LoFi Music](https://unison.audio/lofi-chord-progressions/)
- [Free Tropical Music Loops Wavs Samples Stock Sounds Downloads | Looperman](https://www.looperman.com/loops/tags/free-tropical-loops-samples-sounds-wavs-download)
