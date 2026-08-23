# ca_808 (p-short)

**One-line:** A JUCE-based DAW drum-sequencer plugin that uses cellular-automaton rules, selectable from a ruleset dropdown, to generate evolving 808 drum patterns synced to host tempo.

**Description:** The plugin presents a grid-based GUI representing CA cell states; the grid scrolls right-to-left in sync with the DAW's tempo, and live cell states trigger embedded 808 samples. Per-row mute/solo and click-drag velocity editing are supported, and the roadmap explicitly calls for a combobox letting the user pick which CA ruleset seeds the automaton — i.e., rule selection as a live, user-facing performance parameter rather than a fixed offline choice.

**Core algorithm/technique:** Elementary cellular automaton (specific default rule unspecified in the README) driving a scrolling drum-trigger grid, evaluated live in tempo-synced steps rather than pre-rendered offline.

**License:** Unspecified/none found.

**URL:** [https://github.com/p-short/ca_808](https://github.com/p-short/ca_808)

**Takeaway for this codebase:** This is a UI/workflow cross-check rather than an algorithmic one: this codebase's `generate_ca_drum_pattern`/`_ca_evolve` presumably fix a rule (30/90/110/184) per generation run; ca_808 treats rule choice as a per-row or live-switchable parameter, suggesting a refinement where different drum voices (kick/snare/hat) in `generate_ca_drum_pattern` each run under a *different* CA rule simultaneously (e.g. rule 90 for hats' sparse/fractal feel, rule 30 for chaotic snare ghost-notes) rather than one rule driving the whole kit, which would add per-instrument rhythmic character without new algorithms.
