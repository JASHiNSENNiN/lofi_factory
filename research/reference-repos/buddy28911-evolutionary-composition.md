# evolutionary_composition (Buddy28911)

**One-line:** A senior capstone project using DEAP-based genetic algorithms with human-in-the-loop fitness (0-5 user ratings) to evolve melodies toward listener-preferred styles.

**Description:** Rather than an automated music-theory fitness function, this project makes the human the fitness function: users rate generated melodies 0-5, an elitist selection keeps top performers, crossover swaps measure-halves between two parent melodies (each child gets one parent's first half + the other's second half), and mutation randomly pitch-shifts individual notes. It supports three DEAP algorithm variants (eaSimple, eaMuPlusLambda, eaMuCommaLambda) as swappable evolution strategies, and outputs MIDI with optional arpeggio/scale backing tracks.

**Core algorithm/technique:** Genetic algorithm (DEAP library) with interactive/human fitness evaluation, half-measure crossover, and single-note pitch mutation.

**License:** Unspecified/none found.

**URL:** [https://github.com/Buddy28911/evolutionary_composition](https://github.com/Buddy28911/evolutionary_composition)

**Takeaway for this codebase:** The half-measure crossover operator is a simple, cheap-to-implement operator that could extend `vary_motif`: instead of only retrograde/invert/transpose (which are deterministic single-motif transforms), a "breed two motifs" operator that swaps first-half/second-half material between two existing motifs from the motif engine would add a genuinely new variation family with near-zero implementation cost and no need for a full GA loop (no fitness function, population, or generations required — just the crossover operator itself, invoked directly when the song-form generator wants a "related but different" motif).
