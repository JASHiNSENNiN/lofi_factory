# MCMG - Markov Chain Music Generator (Alexes)

**One-line:** A melody generator using two independent Markov chains — one over pitch, one over duration — trained on an input score and exported as MusicXML.

**Description:** MCMG separates pitch and duration into two decoupled first-order Markov chains rather than a joint state (contrast with SpackiGabriel's project above), training each on a hardcoded input score path and recombining the sampled pitch/duration streams at generation time into a `generated.xml` file viewable in MuseScore. It's a small, single-purpose C#/.NET-style repo (contains a `.sln` file) with modest activity (4 stars, 16 commits).

**Core algorithm/technique:** Two independent first-order Markov chains (pitch chain, duration chain) sampled and zipped together into note events.

**License:** Unspecified/none found.

**URL:** [https://github.com/Alexes/MCMG](https://github.com/Alexes/MCMG)

**Takeaway for this codebase:** This is a useful negative example/cross-check: decoupling pitch and duration chains is simpler to implement than joint-state Markov chains but can produce pitch/rhythm combinations the training data never actually contained (e.g. a long note on a pitch that historically only appeared as a short passing tone) — worth keeping in mind if this codebase ever adds Markov-based melody generation, since the existing CA/Euclidean rhythm generators already separately own "rhythm," a joint pitch-duration chain (or a chain over pitch alone, layered onto the existing rhythm generators) would compose more cleanly than reproducing MCMG's fully-decoupled approach.
