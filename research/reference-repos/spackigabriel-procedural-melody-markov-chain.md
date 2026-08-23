# procedural-melody-generation-markov-chain (SpackiGabriel)

**One-line:** A small Python/music21 Markov-chain melody generator using (pitch, duration) pairs as states, trainable on any sequence of music21 Note objects.

**Description:** States are joint pitch-duration tuples like `('C5', 0.5)` rather than pitch and duration modeled separately, so the chain learns which durations tend to co-occur with which pitches directly from a training melody (the repo demonstrates training on "Ode to Joy"). Generation walks the learned transition table to probabilistically emit a melody of a requested length; the whole thing is a compact, readable single-purpose implementation (`MarkovChainMelodyGenerator.py`, `train_examples.py`, `main.py`).

**Core algorithm/technique:** First-order Markov chain over joint (pitch, duration) states, built with NumPy + music21.

**License:** Unspecified/none found (no license file; 1 star, 10 commits at time of review).

**URL:** [https://github.com/SpackiGabriel/procedural-melody-generation-markov-chain](https://github.com/SpackiGabriel/procedural-melody-generation-markov-chain)

**Takeaway for this codebase:** Since `harmony_engine.py` is already music21-backed, a joint (pitch, duration) Markov state is a cheap, CPU-trivial way to add a third motif-generation mode alongside the existing Euclidean/CA rhythm generators and CFG-based motif engine — train per-song (or per-section) on the CA/Euclidean-driven rhythm skeleton plus a hand-authored lofi melodic corpus, and use the chain as an alternative to `generate_motif` when more "idiomatic" stepwise melodic motion is wanted; joint-state modeling avoids the awkward pitch/duration independence assumption that separate chains (see MCMG below) have to work around.
