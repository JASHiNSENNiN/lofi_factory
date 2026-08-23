---
subgenre_key: anime_lofi
status: existing
bpm_range: [78, 92]              # current code: (80, 94). Sources put "lofi tracks" broadly at 60-95 and general lofi hip-hop at 60-90; anime-lofi/jazzhop specifically (Nujabes-adjacent, cf. nujabes key's own 80-92 band in this codebase) sits comfortably mid-range. Recommend nudging the code's band down slightly (78-92) to sit closer to its clear ancestor (nujabes: 80-92) rather than running hotter than it — anime_lofi should read as a melodically brighter sibling of nujabes, not a faster/more energetic one.
swing_range: [0.57, 0.65]        # matches current code (0.57, 0.65) — general lofi swing convention (10-20%, i.e. roughly 0.55-0.65 in this codebase's swing-ratio terms) supports this; no strong anime-specific swing data found, so keep as-is.
scales: [major_pentatonic, pentatonic_minor, dorian, major]
mood_descriptors: [nostalgic, wistful, dreamy, cinematic, tender]
---

## Harmony
Anime_lofi's harmonic identity is inherited directly from Nujabes' Samurai Champloo soundtrack lineage — jazz-sampled piano voiced in 7th/9th extended chords, slow harmonic rhythm (2-4 chord loops held for bars at a time), same jazz-borrowing logic as the codebase's `nujabes` key but skewed brighter/major rather than nujabes' more dorian/minor-leaning palette. Where nujabes emphasizes moody dorian/natural-minor color, anime_lofi should lean more major_pentatonic/major — the "cherry blossom," "in your own world" aesthetic cited in playlist naming conventions — while still retaining jazz 7th/9th chord extensions rather than plain triads.

## Melody
Sources describe the archetypal arrangement as "sampled jazz piano... mellow saxophone melody" and note vibraphone/mallet instruments plus reverb-soaked koto ("gives off anime vibes") as idiomatic lead/counter-melody choices — both already present in the code's `melody`/`cmelo` GM instrument choices for this key (vibraphone). Melodic phrasing should carry more emotional/cinematic arc than straight jazzhop — wistful, slightly melancholic runs that resolve warmly, echoing the "melancholic piano melody... wistful and dreamy mood" description tied to anime-dialogue-sample-style lofi tracks.

## Rhythm/groove
Boom-bap-lite drums with a clear swing feel and tape saturation, per source description ("boom-bap drums with tape saturation, warm bass") — moderate density, not aggressive, sitting rhythmically between the mellow chill_beats and the more driven hip_hop_lofi. Groove should support rather than compete with the melodic lead, consistent with jazzhop convention generally.

## Arrangement/structure
Loop-based with gentle mood-driven variation; sources note this micro-genre frequently blends vaporwave and cloud-rap textures alongside classic jazzhop, layering digital effects over sampled jazz sources for a "cozy, nostalgic feel." Structurally this supports occasional brighter "cherry blossom" lifts (major-key modal shifts) contrasted with more contemplative dorian passages — giving anime_lofi a wider emotional range within a track than the more tonally consistent nujabes or nostalgic nujabes-adjacent keys.

## Reference repos/algorithms
Direct genre ancestor is Nujabes' catalog (Samurai Champloo OST) and the broader "Jazz Hop Café"/"Tame The Wav" curated-playlist tradition rather than any algorithmic-generation repo; no dedicated anime-lofi generator projects found. Within this codebase, the closest sibling config to model against/differentiate from is `nujabes` (GM_RHODES/GM_VIBRAPHONE/GM_MUTED_TRUMPET, dorian/pent/lydian/natural_minor) — anime_lofi should differentiate primarily via brighter scale bias and koto-adjacent texture rather than a wholesale rhythm/harmony overhaul.

## Provenance
- [The Connection Between Lofi Hip-Hop and Anime | by Alma J. | Medium](https://medium.com/@ochialexander47/the-connection-between-lofi-hip-hop-and-anime-c14ebf1ddc5b)
- [Discover the Ultimate Combo: Lofi and Anime - Musical Flora](https://www.musicalflora.com/genres/lofi/lofi-anime-match-made-heaven/)
- [J-pop & anime chord progressions: 5 patterns | Flat](https://blog.flat.io/jpop-anime-chord-progressions/)
- [Breaking Down 15 Anime Song's Chord Progressions ⋆ Chromatic Dreamers](https://chromaticdreamers.com/analyzing-anime-song-chord-progressions/)
- [How to Make Lofi Music: The Complete Guide - Lunacy Audio](https://lunacy.audio/news/how-to-make-lofi-music/)
- [Top 10 Japanese Inspired Lo-fi Hip-Hop Youtube Channels | Japan Nakama](https://www.japannakama.co.uk/creativity/10-lo-fi-hip-hop-youtube-channels/)
