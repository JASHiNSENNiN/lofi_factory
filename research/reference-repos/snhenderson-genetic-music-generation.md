# Genetic-Music-Generation (SNHenderson)

**One-line:** A from-scratch (non-DEAP) genetic algorithm that evolves songs encoded in ABC notation toward a target, with a CLI exposing population size, generation cap, seed, and cost threshold.

**Description:** Songs are represented as ABC-notation strings and evolved generation-by-generation using a self-written GA (no external GA library), terminating when a configurable cost/fitness threshold is met or a generation cap is hit. A notable feature is reverse-order output mode, which renders the generation sequence from final target back to the initial random piece — useful for visualizing/auditioning how the algorithm converged, not just its final result.

**Core algorithm/technique:** Custom genetic algorithm over ABC-notation-encoded songs with a cost-function-based termination criterion.

**License:** Unspecified/none found.

**URL:** [https://github.com/SNHenderson/Genetic-Music-Generation](https://github.com/SNHenderson/Genetic-Music-Generation)

**Takeaway for this codebase:** The "render the convergence sequence, not just the final result" idea is a good debugging/QA pattern more than an algorithmic one — if a GA-based operator (e.g. voice-leading optimization) is ever added to `harmony_engine.py`, exporting intermediate generations as a sequence of MIDI/audio renders (similar in spirit to `scripts/analytics.py` or `scripts/track_quality.py`'s existing QA outputs) would make it much easier to tune the fitness function by ear rather than only inspecting the final chord progression.
