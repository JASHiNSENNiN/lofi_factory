# GenAI_ChordRhythmChain_Music (takakhoo)

**One-line:** A personal collection of classical generative-music algorithm implementations in one Python repo: L-systems for chord progressions, Markov chains for melody, a Game-of-Life-style cellular automaton for drum patterns, and a genetic algorithm for melody harmonization.

**Description:** `my_lsystem.py` applies Lindenmayer-system string rewriting to chord *symbols* rather than notes — treating chords as the alphabet being rewritten, which is a different target than the more common "L-system for melodic pitch/rhythm" approach seen elsewhere in this survey (e.g. ephemeralwaves' module). `markov_melody.py` is a standard note-transition-probability melody chain; `cellular_automaton.py` explicitly cites Conway's Game-of-Life-style grid evolution (2D, not the 1D elementary automata used elsewhere) for drum-pattern generation; `genetic_melody_harmonizer.py` evolves chord progressions against a fixed melody using music-theory-based fitness. All four techniques are music21-based and output MIDI; music21 is the only hard dependency for the generative logic (TensorFlow appears listed among project dependencies but the four generative modules described are classical/rule-based, not neural).

**Core algorithm/technique:** Four independent, hand-rolled techniques in one repo: L-system chord-symbol rewriting, Markov-chain melody generation, 2D (Game-of-Life-style) cellular-automaton drum patterns, and genetic-algorithm melody harmonization — good as a single-repo cross-section of this whole survey's five categories.

**License:** Unspecified/none found.

**URL:** [https://github.com/takakhoo/GenAI_ChordRhythmChain_Music](https://github.com/takakhoo/GenAI_ChordRhythmChain_Music)

**Takeaway for this codebase:** The 2D Game-of-Life-style CA for drums is a concrete alternative worth cross-checking against this codebase's 1D elementary automata (`_ca_step`/`_ca_evolve`, rules 30/90/110/184): a 2D grid (e.g. rows = drum voices, columns = time steps, Game-of-Life birth/survival rules) naturally couples different drum voices' evolution to each other in a way 1D per-voice automata don't, which could produce more musically-coordinated kick/snare/hat interplay (e.g. a hi-hat cell "dies" from overcrowding when kick+snare are both active) — worth a small experimental branch if the existing 1D CA patterns ever feel too independent-per-voice.
