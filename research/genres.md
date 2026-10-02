# Genre sources: what defines each sub-genre, and what the code does

A review of the sources behind `config/genres/*.yaml`, written for the genre
rework. Older, deeper notes on individual genres are in `research/subgenres/`
and on rhythm, mixing and harmony in `research/theory/`; this file is the
short reference that ties each genre's settings to a source.

Practitioner guides (producer blogs, drum-pattern sites) are the main sources
here because there is little academic work on these microgenres. Where a
peer-reviewed or reference source exists, it is used first.

## Cross-cutting findings

| Finding | Source | What the code does |
|---|---|---|
| Lofi hip hop sits at 70–90 BPM, most "radio" content at 80–85, with swung 16ths around 60%, 7th/9th chords on electric piano, an 8–10 kHz low-pass and vinyl noise. | [bpmcalc.com](https://bpmcalc.com/genres/lo-fi/), [Mixed In Key](https://mixedinkey.com/captain-plugins/wiki/how-to-make-lofi-hip-hop/), [MODE Audio](https://modeaudio.com/magazine/lofi-hip-hop-5-production-essentials) | Hip-hop-family genres stay in 70–92 BPM with swing 0.58–0.69, extended voicings and the lofi FX chain. |
| Sleep playlists are slower, softer, lower-energy and more instrumental/acoustic than general music (225,626 tracks; tempo 105 vs 120 BPM, energy 0.23 vs 0.59, acousticness 0.74 vs 0.35). | Scarratt et al., *PLoS One* 2023, ["The audio features of sleep music"](https://pmc.ncbi.nlm.nih.gov/articles/PMC9847986/) | `sleep_lofi` 58–68 BPM, low energy, new-age pad; `ambient` beatless. |
| General MIDI program and drum-note numbers (e.g. cowbell 56, side stick 37, clap 39, shaker 82; agogo 114, saw lead 82, polysynth pad 91 in 1-indexed form). | [General MIDI (Wikipedia)](https://en.wikipedia.org/wiki/General_MIDI), [GM percussion key map (CMU)](https://www.cs.cmu.edu/~music/cmp/archives/cmsip/readings/GMSpecs_PercMap.htm) | `scripts/gm_instruments.py` (0-indexed) and the drum-note constants in `composer.py`. |
| The audio drum layer and the MIDI drums must play the same rhythm; two unrelated patterns at once is not a groove. | (engineering finding in this repo) | `drum_sampler.pattern_from_midi()`: the sample layer now doubles each section's MIDI pattern. |
| Euclidean/cellular-automaton rhythms carry no genre information. | (engineering finding; see `research/theory/rhythm-groove.md`) | Only `study_lofi` and `chill_beats` (`generated_drums: true`) may use them. They used to replace the genre's groove in ~48% of sections of every genre. |

## Per genre

| Genre | Defining traits (sources) | Settings now |
|---|---|---|
| `lofi_house` | 115–125 BPM, four-on-the-floor kick, dusty filtered chords ([vibesdj.io](https://vibesdj.io/dj-tools/house-bpm-chart), [Dirty Disco](https://www.dirtydiscoradio.com/lo-fi-deep-house/)) | Pattern R (kick every beat, clap 2 and 4, off-beat open hats), synth bass, organ stabs, 110–128 BPM, near-straight 16ths. Before: no four-on-the-floor pattern at all. |
| `bossa_lofi` | Steady 8th hats, side-stick clave (3+2 over two bars), bass drum on 1 and 3 with pickups, no backbeat snare; nylon-guitar comping; lofi bossa sits around 64–90 BPM ([kickdrum.io](https://kickdrum.io/patterns/bossa-nova), [Tunable](https://tunableapp.com/rhythm/bossa-nova-rhythm/), [Acoustic Guitar](https://acousticguitar.com/video-lesson-learn-basic-bossa-nova-patterns-inside-and-out/), `research/subgenres/bossa_lofi.md`) | Two-bar pattern S, nylon guitar chords, flute lead, upright bass, straight 8ths. Before: vibraphone chords and an Afrobeat pattern. |
| `lofi_synthwave` | 80–118 BPM (sweet spot ~100), four-on-the-floor, gated big snare on 2 and 4, saw leads, 8th/16th arpeggios, synth bass ([Orphiq](https://orphiq.com/resources/what-is-synthwave), [UJAM](https://www.ujam.com/tutorials/how-to-synthwave-drum-patterns/), [Synth Centric](https://www.synthcentric.com/articles/a-guide-to-synthwave)) | Pattern T, polysynth chords, saw-lead arpeggiator, synth bass, 82–104 BPM (inside the project's lofi tempo limit), straight timing. Before: vibraphone arpeggio over hip-hop drums. |
| `lofi_phonk` | Memphis-rooted; the cowbell line is the signature; distorted, sliding 808s; classic phonk 60–80 BPM, drift phonk 130–160 ([Melodics](https://melodics.com/blog/producers-guide-to-phonk-music), [Futureproof](https://futureproofmusicschool.com/blog/what-is-phonk)) | Pattern Q with a real GM cowbell (was a side-stick), agogo bell lead as the pitched cowbell riff, gliding 808-style sub, trap half-time. Generic lofi patterns removed from its pool. |
| `lofi_drill` | UK drill ~140 BPM felt in half time (~70), sliding 808s, triplet hats, off-beat snare ([se7enbeatlab](https://se7enbeatlab.com/bpm/uk-drill/), [Amped Studio](https://ampedstudio.com/blog/what-is-drill-music/), [Wikipedia](https://en.wikipedia.org/wiki/UK_drill)) | Half-time 72–88, triplet hats, 808 glide (existing), now a dark piano lead and an 808-style sub. |
| `lofi_garage` | UK garage / 2-step 130–140 BPM, skipping kick, shuffled hats ([bpmcalc.com](https://bpmcalc.com/genres/garage/), [Native Instruments](https://blog.native-instruments.com/uk-garage-music/)) | Kept as the documented half-time equivalent (66–76; `research/subgenres/lofi_garage.md`). Known limit: a 16-step grid at half time can't hold 2-step's 16th syncopation. |
| `city_pop` | 90–110 BPM, maj7/9/m11 harmony, slap bass, clean chorused 16th-note guitar, brass/sax, boogie/disco drums ([after5.fr](https://after5.fr/en/2023/city-pop/city-pop-music-theory-en/), [beatkey](https://beatkey.app/how-to-make-city-pop-music)) | Slap bass, clean-guitar counter line, alto sax lead, funk and four-on-the-floor patterns, 90–108 BPM, straight 16ths. |
| `vaporwave` | Slowed (60–80% speed) 80s/90s smooth jazz, R&B and muzak, 60–90 BPM, heavy reverb ([Wikipedia](https://en.wikipedia.org/wiki/Vaporwave), [Futureproof](https://futureproofmusicschool.com/blog/techniques-for-how-to-make-vaporwave-music-with-authentic-style)) | Electric piano, alto sax, fretless bass, warm pad; trap drum samples removed. |
| `nujabes` (jazz boom bap) | Modal-jazz samples over boom-bap drums, piano, sax and flute, 85–95 BPM with strong swing ([jazz.fm](https://jazz.fm/nujabes-jazz-samples-lofi-hip-hop/), [Melodigging](https://www.melodigging.com/genre/jazz-boom-bap)) | Acoustic piano, flute lead, tenor sax counter line, upright bass. The internal key is a real artist's name; it's published as "jazz hop" (`_SUBGENRE_TO_GENRE_LABEL`). |
| `neo_soul` | Extended 9th/11th/13th chords, Rhodes as the defining keyboard, drums with per-voice timing offsets (snare behind, hats ahead), 82–92 BPM ([emastered](https://emastered.com/blog/neo-soul-chord-progressions), [drum.town](https://drum.town/lessons/hiphop-j-dilla/), [RouteNote](https://create.routenote.com/blog/the-dilla-swing-how-one-producer-humanised-the-sound-of-hip-hop/)) | Rhodes chords (was electric piano 2), finger bass (was slap), per-voice micro-swing. |
| `lofi_jazz`, `jazz_cafe` | Ride-cymbal "spang-a-lang", hi-hat foot on 2 and 4, walking quarter-note bass ([Jazz Night School](https://jazznightschool.org/pages/basic-4-4-swing-beat-for-drummers), [Drum Helper](https://drumhelper.com/learning-drums/jazz-drum-beats-and-patterns/)) | Ride-led patterns (existing), upright bass (was fretless), walking bass always on. |
| `piano_lofi`, `lofi_classical`, `anime_lofi` | Piano-led; anime lofi favours piano melodies and the IV–V–iii–vi "royal road" ([Skoove](https://www.skoove.com/blog/anime-piano-songs/), [Motifkit](http://motifkit.com/lofi-chord-progressions/)) | Acoustic grand piano (before: no genre used an acoustic piano). |
| `bedroom_pop` | Clean, warm, chorused/jangly guitar, soft drums, 60–110 BPM ([Guitar Chalk](https://www.guitarchalk.com/bedroom-pop-amp-settings/), [Melodigging](https://www.melodigging.com/genre/bedroom-pop)) | Clean electric guitar chords, vibraphone lead, finger bass. |
| `lo_fi_funk` | Slap bass, clavinet, wah guitar, ghost-note drums; lofi funk runs slower than funk's 90–130 ([Lunacy](https://lunacy.audio/news/how-to-make-lofi-music/)) | Slap bass, clavinet stabs (texture), funk patterns, 82–96 BPM. |
| `ambient`, `sleep_lofi` | Sustained pads, slow harmony, usually no drums ([EDMProd](https://www.edmprod.com/what-is-ambient-music/), Scarratt et al. 2023 above) | `ambient`: no drums at all; new-age pad. `sleep_lofi`: sparse drums, new-age pad. |
| `lofi_world` | Hindustani markers in this preset: sitar, gamaka ornaments, 7-beat Rupak tala | One tradition: sitar lead, flute counter line (bansuri stand-in). The Japanese koto and African kalimba were removed. |

## Known limits

- General MIDI through a soundfont is not a sampled record. Vaporwave's
  "slowed sample" sound, phonk's Memphis vocal chops and garage's vocal chops
  can only be approximated.
- Patterns are 16 steps per bar (32 for two-bar patterns). 32nd-note phonk
  rolls and half-time 2-step syncopation are approximations.
- Several genres still share the hip-hop pattern family (chillhop, study,
  morning, cozy, summer). They differ mainly by instruments, tempo and mix,
  which matches how those playlists are actually described.
