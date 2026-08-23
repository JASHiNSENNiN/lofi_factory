# subsequence (simonholliday)

**One-line:** A stateful, generative MIDI sequencer/composition engine for Python that rebuilds patterns every cycle from Euclidean rhythms, cellular automata, L-systems, and Markov chains, driven by live harmonic/section context.

**Description:** Unlike a fixed-loop sequencer, `subsequence` regenerates each pattern per cycle with awareness of current chord, song section, cycle count, and data shared between generators — so a Euclidean hi-hat pattern can "thin itself as tension builds," or a cellular-automaton pattern can be reseeded directly from the active harmony. It ships a hybrid sleep+spin-wait timing loop that holds pulse jitter under ~5 microseconds on Linux, using absolute offsets from session start to avoid cumulative drift, aimed at live-performance use.

**Core algorithm/technique:** Combines four classic generative building blocks in one shared runtime: Euclidean rhythm generation, elementary cellular automata (seedable from harmonic state), L-systems, and Markov chains (with a roadmap item for MIDI-file-trained chains). The novel part isn't any one algorithm but the shared "regenerate-per-cycle with context" architecture tying them together.

**License:** GNU AGPLv3 (commercial licensing available on request); core dependencies are MIT/BSD-3-Clause/Unlicense.

**URL:** [https://github.com/simonholliday/subsequence](https://github.com/simonholliday/subsequence)

**Takeaway for this codebase:** The "seed the CA from current harmony" idea is directly applicable to `generate_ca_drum_pattern`/`_ca_evolve` in `scripts/generate_music_gemini.py` — currently CA rules likely run with a fixed or random seed row; deriving the CA's initial row from the active chord (e.g., scale-degree parity, chord-tone bitmask) would let drum density/texture track harmonic tension the way this project does, and would compose well with the existing 5-form/CFG song-structure system for section-aware pattern evolution.
