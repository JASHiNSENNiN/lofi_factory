---
subgenre_key: bossa_lofi
status: existing
bpm_range: [70, 90]              # code currently uses (74, 88), a very good match — the specific "lo-fi bossa nova" fusion genre (as opposed to traditional bossa nova, which runs 100-145 BPM) is explicitly documented at 64-88 BPM by sample-pack producers. Current range sits almost exactly in the documented lofi-bossa pocket; only a tiny adjustment recommended (drop floor slightly to 70, keep ceiling near 88-90).
swing_range: [0.50, 0.58]        # code currently uses (0.52, 0.60), close. Traditional bossa nova uses straight (not swung) 8th notes as its defining rhythmic trait, but "should sit in the middle of a scale of swing" — too straight feels "uninformed." Current range is appropriately the straightest of the 13, keep near-identical.
scales: [major, dorian, pent, major_pent]
mood_descriptors: [intimate, sophisticated, breezy, understated, romantic]
---

## Harmony
Bossa nova is jazz harmony filtered through Brazilian voice-leading conventions — heavy use of ii7-V7-Imaj7 but with far more chromatic root motion and modal interchange than typical American jazz standards. Jobim's signature techniques: prolonging the dominant II7 (rather than resolving quickly) for extra brightness, tritone substitutions of V creating smooth chromatic bass lines, and the distinctive bIImaj7-Imaj7 half-step-down resolution (e.g. Dbmaj7 to Cmaj7) — a chord move essentially unique to this subgenre among the 13. Major 7th chords are the default tonic sonority (not plain triads), and four-chord loops that add one extra chromatic step to the basic ii-V-I are common, giving bossa its longer, more "elaborate harmonic sentences" than the code's other, simpler progressions.

## Melody
Smooth, vocal-derived phrasing with minimal rhythmic activity — closer to a sung melody's natural contour than an instrumental "lick." Flute and nylon guitar (both already in the current instrument config) trade melodic duty, often with light ornamentation but few large leaps; the mood is conversational and unhurried, per Astrud Gilberto's famously breathy, understated vocal delivery style that shaped the genre's melodic sensibility even in instrumental form.

## Rhythm/groove
The "batida" — João Gilberto's syncopated fingerstyle guitar pattern derived from the samba tamborim rhythm — is bossa's genre-defining rhythmic cell: alternating bass notes (root/5th) on the beat played with the thumb, syncopated chord strums layered by the fingers. Straight (unswung) 8th notes distinguish it from swing-based jazz, though a slight "sway" keeps it from feeling stiff. Drums (when present) are light brushes plus shaker/tamborim/rim-click maintaining a subtle samba pulse rather than a hip-hop-style kick/snare backbeat.

## Arrangement/structure
Traditional bossa nova uses 32-bar AABA (or verse-refrain) song form with short intros/codas — head-arrangement style where one set of bars repeats with the melody stated, then implied under a "solo." **This AABA form does not currently exist in the codebase's five song forms** (standard/ambient/funk/minimal/extended — all variations on an I-A-BR-B-O template); implementing bossa_lofi with real genre fidelity would benefit from a dedicated AABA-shaped song-form entry. Instrumentation core: nylon-string guitar (the batida supplies rhythm+bass+harmony at once), light brushed drums/shaker/tamborim, upright or electric bass, piano/electric piano, with flute/soft horns trading the lead.

## Reference repos/algorithms
None specific — general bossa-nova theory/rhythm-pattern references (Learn Jazz Standards, Liberty Park Music) rather than a codified generative algorithm.

## Provenance
- [Bossa Nova Chord Progressions: Brazilian Jazz + MIDI — ChordGen](https://www.chordgen.org/chords/bossa-nova)
- [The Jobim Chord Progression — Piano With Jonny](https://pianowithjonny.com/piano-lessons/the-jobim-chord-progression/)
- [6 Bossa Nova Chord Progressions You Need To Know! — Learn Jazz Standards](https://www.learnjazzstandards.com/blog/bossa-nova-chord-progressions/)
- [Rhythm Rules: Brazilian Guitar 101 — Premier Guitar](https://www.premierguitar.com/rhythm-rules-brazilian-guitar-101)
- [Bossa Nova Guitar Patterns – 5 Levels You Need To Know — Jens Larsen](https://jenslarsen.nl/bossa-nova-guitar-patterns-5-levels-you-need-to-know/)
- [Astrud Gilberto spread bossa nova to a welcoming world — The Conversation](https://theconversation.com/astrud-gilberto-spread-bossa-nova-to-a-welcoming-world-but-got-little-love-back-in-brazil-207271)
- [The Girl From Ipanema – The Story Behind the Song — Jazzfuel](https://jazzfuel.com/girl-from-ipanema-story/)
- [could you explain a bossa to me? — TalkBass](https://www.talkbass.com/threads/could-you-explain-a-bossa-to-me.318020/)
- [A Guide to Drum Kit Notation for Latin Music: Bossa Nova — Liberty Park Music](https://www.libertyparkmusic.com/guide-drum-kit-notation-latin-music-bossa-nova/)
- [Guide to Brazilian Bossa Nova Music — MasterClass](https://www.masterclass.com/articles/guide-to-brazilian-bossa-nova-music)
- [Lo-Fi Bossa Nova – Sample Packs — House of Loop](https://houseofloop.com/downloads/lo-fi-bossa-nova/)
