# Chord progression with genetic algorithm (Santiago Chio, blog + code)

**One-line:** A DEAP-based genetic algorithm that generates a four-voice chord progression harmonizing a given bass line, using MIDI-number pitch encoding and LilyPond output for sheet-music visualization.

**Description:** Each individual is a sequence of four-note chords (MIDI pitch numbers, e.g. middle C = 60); the key signature fixes an initial sharps/flats context, and a bank of predefined chord shapes (as intervals from a root, both major and minor) constrains what mutation/crossover can produce so the search space stays harmonically plausible rather than fully unconstrained. Selection favors progressions scoring well against implied voice-leading-smoothness and harmonic-function criteria (tonic/subdominant/dominant relationships), evolved via DEAP's built-in selection/crossover/mutation operators.

**Core algorithm/technique:** Genetic algorithm (DEAP) for four-part chord-progression harmonization against a fixed bass line, constrained by a predefined chord-shape vocabulary rather than free pitch search.

**License:** Unspecified/none found (personal blog post with accompanying code; no explicit license stated).

**URL:** [http://schiob.github.io/programming/2015/12/08/chord-progression-with-genetic-algorithm/](http://schiob.github.io/programming/2015/12/08/chord-progression-with-genetic-algorithm/)

**Takeaway for this codebase:** The key design choice worth stealing is constraining the GA's search space with a predefined chord-shape vocabulary (rather than raw pitch mutation) — since `harmony_engine.py` already generates chord progressions including secondary dominants via music21, a natural extension is a lightweight GA/simulated-annealing voice-leading *post-pass* that takes the existing chord symbols as fixed harmonic content and only searches over inversions/voicings/octave placements to minimize total voice movement between consecutive chords, which is a much smaller and cheaper search than full progression generation and would directly improve the smoothness of `harmony_engine.py`'s output without touching its existing chord-choice logic.
