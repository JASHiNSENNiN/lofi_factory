---
subgenre_key: city_pop
status: existing
bpm_range: [90, 108]              # current code: (78, 92). Sources are consistent and specific: "city pop lives in the 95-120 BPM range, with mid-tempo groove being a defining characteristic," distinctly faster than lofi hip-hop. The current code value (78-92) undershoots this significantly and overlaps almost entirely with cozy_cafe/anime_lofi — recommend raising substantially to 90-108 (capped below full disco/funk 120 to stay lofi-compatible) so city_pop reads as the roster's clear "driving, funk-groove, up-tempo" outlier rather than blending into the mid-70s-90s cluster.
swing_range: [0.53, 0.60]        # current code: (0.55, 0.63). Sources give a precise figure: "city pop typically uses 8-12% swing on 16th-note hi-hats — too much feels lo-fi, too little feels stiff," explicitly calling out that heavier swing reads as generic lo-fi, not city pop's polished restraint. Recommend tightening the band down to 0.53-0.60 (lighter/more restrained than the current 0.55-0.63) to encode that distinction — city_pop should swing less than cozy_cafe/bedroom_pop, not more.
scales: [major, major_pentatonic, dorian]
mood_descriptors: [glossy, nocturnal, sophisticated, nostalgic-urban, driving]
---

## Harmony
City pop's defining feature versus ordinary pop is harmonic sophistication: "standard pop uses triads; city pop uses extensions — major 7ths, dominant 9ths, minor 11ths," with intricate chord substitutions throughout (per analysis of Yamashita/Takeuchi catalog, e.g. "Plastic Love"). This should push city_pop's chord voicings toward the densest jazz-fusion extensions in the bright/cozy cluster — richer than cozy_cafe's maj7/9 warmth, closer to lofi_jazz's sophistication but in a major/funk-driven rather than moody-dorian frame. Frequent secondary dominants and passing chords (borrowed from the genre's AOR/soft-rock/jazz-fusion lineage) are idiomatic.

## Melody
Lead melody should carry a "warm-toned electric guitar as main lead" quality (per production-guide sources) — the code's GM_FLUTE melody choice is a reasonable substitute timbre-wise but the phrasing should aim for confident, songful, funk-inflected lines rather than the breathy/gentle phrasing appropriate to morning_lofi. Major and major-pentatonic color dominate, with occasional dorian coloring for funk edge; melodic movement should feel propulsive and "driving through neon-lit streets" rather than static/contemplative.

## Rhythm/groove
This is the genre's most rhythmically specific profile in the whole roster: "four-on-the-floor or half-time kick, snare on beats 2 and 4, 16th-note hi-hats with slight swing, and a classic open hat on the disco upbeat position (beat 1.75)," rooted in disco and jazz-funk. Prominent, syncopated basslines and "funky drum fills" are essential — city_pop should be the most overtly funk/disco-groove-driven of the bright/cozy cluster, distinct from the boom-bap-lite feel shared by cozy_cafe/morning_lofi/anime_lofi. The engine's existing GM_GUITAR_JAZZ cmelo choice supports funk-comping texture well.

## Arrangement/structure
"Midnight cruise through neon-lit city streets" — arrangement should feel polished and driving rather than laid-back-static, with funky drum fills at section boundaries and a full-band feel (guitar lead, piano/synth harmony, groovy bass, tight full drum kit) rather than the sparser textures of piano_lofi or bedroom_pop. Sources note City Pop's producers deliberately preserved "subtle timing variations" even amid advanced studio tech — i.e., tight but not robotically quantized, a "restrained" version of the tight groove city_pop.

## Reference repos/algorithms
No dedicated city-pop MIDI-generation repos found; the genre's core reference is the 1970s-80s Japanese catalog itself (Tatsuro Yamashita's "For You," Mariya Takeuchi's "Variety"/"Plastic Love," Casiopea for the jazz-fusion-adjacent groove vocabulary). Sample-pack products like "City Pop Night Drive" (Black Octopus Sound) are useful as an ear-reference for the funk-groove/synth-bass palette even though not open-source/algorithmic.

## Provenance
- [The Chords of City-Pop - JasLikesJazz](https://jaslikesjazz.wordpress.com/2022/05/18/the-chords-of-city-pop/)
- [How to Make City Pop Music: Production Guide (BPM, Chords, Samples)](https://beatkey.app/how-to-make-city-pop-music)
- [What is City Pop? The Producer's Guide to Classic Japanese Pop | Baby Audio](https://babyaud.io/blog/what-is-city-pop)
- [The basic information about Japanese City Pop Music | by Sora Satoh | Medium](https://sorasatoh.medium.com/the-basic-information-about-japanese-city-pop-music-fd78f225ea4e)
- [Tatsuro Yamashita — Wikipedia](https://en.wikipedia.org/wiki/Tatsuro_Yamashita)
- [Plastic Love — Wikipedia](https://en.wikipedia.org/wiki/Plastic_Love)
- [City Pop: A Guide To Japan's Overlooked '80s Disco In 10 Tracks | Telekom Electronic Beats](https://www.electronicbeats.net/city-pop-guide-japans-overlooked-80s-disco-10-tracks)
