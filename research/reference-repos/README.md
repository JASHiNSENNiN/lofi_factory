# Reference repos survey

Cross-check survey of procedural/generative music projects across 5 categories, run against this codebase's existing Euclidean (`scripts/euclidean.py`), Wolfram CA (`generate_ca_drum_pattern`/`_ca_step`/`_ca_evolve` in `scripts/generate_music_gemini.py`), CFG song-form (`_SONG_FORMS`/`generate_song_form()`), motif engine (`generate_motif`/`vary_motif`), and music21 harmony engine (`scripts/harmony_engine.py`).

## Repos with dedicated files

**Category 1 — lofi hip-hop generators**
- [simonholliday-subsequence.md](simonholliday-subsequence.md) — stateful Python MIDI sequencer combining Euclidean/CA/L-system/Markov with context-aware regeneration per cycle. AGPLv3.
- [cyu2019-lofibot.md](cyu2019-lofibot.md) — sample-remix (librosa/pydub) lofi generator from a short input loop, not symbolic composition. No license found.
- [jacek-mcp-lofi-music-generator.md](jacek-mcp-lofi-music-generator.md) — dual-RNN (melody + chords) lofi generator, triple-embedding tokenization. **DL/GPU, reference only.** No license found.
- [jacbz-lofi.md](jacbz-lofi.md) — PyTorch VAE + Tone.js web synth lofi generator. **DL/GPU, reference only.** Apache License.

**Category 2 — Markov chain music generation**
- [spackigabriel-procedural-melody-markov-chain.md](spackigabriel-procedural-melody-markov-chain.md) — joint (pitch, duration) state Markov chain, music21-based. No license found.
- [alexes-mcmg.md](alexes-mcmg.md) — decoupled pitch chain + duration chain, MusicXML output. No license found.
- [kstar-markov-music.md](kstar-markov-music.md) — staged unigram→n-gram Markov pipeline trained on Bach violin concertos. No license found.

**Category 3 — L-system / grammar-based generation**
- [ephemeralwaves-l-system-music-module.md](ephemeralwaves-l-system-music-module.md) — Koch-curve L-system mapped to pentatonic melodic steps. GPL-3.0.
- [tener-procogram.md](tener-procogram.md) — probabilistic CFG melody generation with interactive listen-and-vote loop. BSD-3-Clause.

**Category 4 — Cellular automaton rhythm/music**
- [p-short-ca_808.md](p-short-ca_808.md) — JUCE plugin, live tempo-synced CA-driven 808 drum sequencer. No license found.
- [lilyhahn-musica.md](lilyhahn-musica.md) — Rule 30 CA driving both visuals and real-piano-sample audio. GPL-2.0.

**Category 5 — GA / simulated-annealing voice leading & harmony**
- [buddy28911-evolutionary-composition.md](buddy28911-evolutionary-composition.md) — DEAP GA with human-rating fitness, half-measure crossover. No license found.
- [snhenderson-genetic-music-generation.md](snhenderson-genetic-music-generation.md) — custom GA over ABC-notation songs, reverse-convergence output mode. No license found.
- [schiob-chord-progression-genetic-algorithm.md](schiob-chord-progression-genetic-algorithm.md) — DEAP GA harmonizing a bass line with constrained chord-shape vocabulary. No license found.

**Cross-category**
- [takakhoo-genai-chordrhythmchain-music.md](takakhoo-genai-chordrhythmchain-music.md) — one repo covering all 4 classical techniques: L-system chord rewriting, Markov melody, 2D Game-of-Life-style CA drums, GA harmonization. No license found.

## Other repos/projects surfaced during search (not given dedicated files — duplicative of above or DL-only with no distinct algorithmic detail)

- arman-aminian/lofi-generator, sagnibak/lofAI, Melo04/lofi-generator-LSTM, zacharykatsnelson/Lofi-Hip-Hop-Generator, AryanNanda17/NonStop-Lofi-Vibe-Generator, mtsandra/lofi-station, khcr/autofy — additional lofi generators, all LSTM/RNN/VAE deep-learning approaches (GPU-oriented), redundant with jacek-mcp and jacbz already documented in depth.
- mnagel/markov, DanGOTO100/Machine-Learning-Automatic-Music-Markov-Chain — additional Markov melody generators, redundant with the three Markov repos documented above.
- nylki/lindenmayer — general-purpose (non-music) JS L-system library referenced as the engine class ephemeralwaves' module is inspired by.
- brunoventura/automata-music, plhosk/music-of-life — additional CA music generators (non-deterministic/2D-Game-of-Life style respectively), redundant with p-short/ca_808 and lilyhahn/musica.
- METACREATION's "Music by Genetic Algorithm" (Vox Populi) and a GVSU academic paper ("A Genetic Algorithm for Musical Chord Progression Generation," trained on 890 Billboard Top 100 songs with conditional-probability fitness penalties) — academic/lab work referenced for context; GVSU PDF was not directly fetchable (403), summarized from search only.
- Prusinkiewicz's foundational "Score Generation with L-systems" (ICMC 1986) and Jon McCormack's "Grammar Based Music Composition" — the original academic papers underlying the L-system-for-music approach used by ephemeralwaves' module and referenced conceptually by ProCoGraM/takakhoo's chord-rewriting approach.

## Summary

15 repos/projects documented in dedicated files, spanning all 5 requested categories (lofi generators, Markov chains, L-systems/grammars, cellular automata, GA/evolutionary harmony). ~30+ distinct repos/projects/papers surfaced total across the research process.
