---
subgenre_key: lofi_classical
status: existing
bpm_range: [56, 74]              # current code: (58, 78). Recommend trimming the top from 78 to 74 — sources on neoclassical/Max Richter/Nils Frahm reference material lean toward slow, cinematic, "fragile staccato tension" builds rather than up-tempo material, and the current 78 ceiling edges into piano_lofi/cozy_cafe territory. Keep the low end similar (56 vs 58) to preserve the beatless-adjacent, rubato-friendly floor consistent with the genre's classical-chamber-music ancestry.
swing_range: [0.50, 0.56]        # current code: (0.50, 0.57). Sources describe neoclassical/chamber-string composition as fundamentally straight-time/rubato (staccato tension, orchestral builds, string-quartet writing) rather than swung — the genre's defining rhythmic gesture is expressive tempo rubato, not groove-quantized swing. Recommend keeping this the straightest-feeling profile alongside ambient/vaporwave; trimmed the top slightly (0.56 vs 0.57) for consistency, negligible practical change.
scales: [major, lydian, major_pentatonic, harmonic_minor]
mood_descriptors: [cinematic, elegant, wistful, stately, luminous]
---

## Harmony
Lofi_classical should draw on genuine classical-harmony devices beyond jazz-extension vocabulary: secondary dominants, borrowed chords from the parallel minor, and — distinctively per neoclassical convention — "the dominant 7th chord in the minor key... for the mellow vibes of a minor key and the hard tension of a 7th chord," a specifically neoclassical harmonic fingerprint worth differentiating from the code's other minor-leaning keys (dark_lofi, lofi_drill). Max Richter-style writing frequently pairs simple, singable harmonic movement with orchestral coloring (string quartet plus an added second cello, "for added depth, warmth, and resonance") rather than jazz-club chord density — favor clarity and consonance over extended-chord sophistication, distinguishing lofi_classical from the jazzier piano_lofi.

## Melody
Melody should be string-led or piano-led with a cinematic, through-composed quality — Max Richter/Nils Frahm pieces are cited as evolving "from fragile staccato tension" toward fuller statements, and blending "intimate piano arpeggios, nylon guitar, cello drones, and epic orchestral build-ups." This argues for the code's GM_CELLO melody voice carrying long, arcing lines with real dynamic development (quiet opening, fuller climax) rather than the tight motif-loop approach suited to piano_lofi — lofi_classical should feel like the most "composed"/least "looped" subgenre in the roster.

## Rhythm/groove
Largely rubato/pulse-optional — classical chamber convention (staccato-to-legato dynamic arcs, orchestral swells) doesn't map to a boom-bap or swung-groove feel at all. Where a percussive pulse exists, it should be the sparsest and most textural in the roster (softer than even ambient's minimal pulse would be, given lofi_classical retains more harmonic motion), functioning as gentle punctuation rather than a groove anchor.

## Arrangement/structure
Structure should favor a clear dynamic arc — quiet, intimate opening; a gradual, orchestral-scale build (Richter/Frahm's "epic orchestral build-ups"); and release — rather than the loop-and-vamp structure of ambient or the steady-state repetition of study_lofi. Blending "organic with electronic" (a cited lofi convention: electronic drum textures under organic string/piano lines) is acceptable but should stay subordinate to the string/piano foreground. Washy reverb on sampled strings is a commonly cited lofi-classical-crossover production technique worth leaning into via the engine's reverb/soundfont choices.

## Reference repos/algorithms
No dedicated lofi-classical algorithmic generators found; the clearest reference corpus is the contemporary-classical/neoclassical catalog itself — Max Richter (The Blue Notebooks, On the Nature of Daylight), Nils Frahm (piano + analog synth + ambient texture blends), and Ólafur Arnalds — valued for harmonic-arc and orchestration technique rather than algorithmic pattern. VST plugins modeling this string sound (e.g. "Max Richter Strings" style libraries) confirm the augmented-cello-section voicing approach as a genre convention worth encoding in future cmelo/pad layering.

## Provenance
- [Neo-classical — Goethe-Institut Ireland](https://www.goethe.de/ins/ie/en/kul/mag/20771217.html)
- [Nils Frahm — Wikipedia](https://en.wikipedia.org/wiki/Nils_Frahm)
- [Max Richter Strings - Max Richter VST Plug-in – SRM Sounds](https://srmsounds.com/products/max-richter-strings)
- [Modern Piano Essentials: The Felt Revolution](https://klangspot.com/modern-piano-essentials-the-ultimate-spotify-playlist-for-contemporary-classical-neoclassical-music/)
- [Mastering Lofi and Neo-Soul Chords on Guitar: A Jazzy Journey - Breakthrough Guitar](https://breakthroughguitar.com/mastering-lofi-and-neo-soul-chords-on-guitar-a-jazzy-journey-rotem-sivan/)
- [LoFi Chord Progressions: The 6 Best Chord Progressions for LoFi Music](https://unison.audio/lofi-chord-progressions/)
