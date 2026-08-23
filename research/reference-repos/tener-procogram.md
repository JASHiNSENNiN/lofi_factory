# ProCoGraM (Tener)

**One-line:** A Haskell tool that generates melodies from probabilistic context-free grammars (PCFGs), with an interactive listen-and-vote loop for evolving which grammar variant to keep.

**Description:** Terminal symbols represent individual notes/rests with fixed durations; non-terminals carry production rules where each expansion option is weighted by a probability (all options for a symbol summing to 1), and generation works by repeatedly expanding non-terminals starting from a start symbol until only terminals remain — structurally identical to the CFG approach this codebase already uses for song-form generation, just applied at the note/phrase level instead of the section level. A key implementation constraint: every non-terminal must have nonzero probability of eventually bottoming out in terminals, to guarantee generation terminates. The tool is interactive — users audition a generated grammar's output via FluidSynth/timidity, vote, and the tool evolves which grammar to explore next, with session save/resume and history navigation.

**Core algorithm/technique:** Probabilistic (stochastic) context-free grammar for melodic sequence generation, with human-in-the-loop grammar selection.

**License:** BSD-3-Clause.

**URL:** [https://github.com/Tener/ProCoGraM](https://github.com/Tener/ProCoGraM)

**Takeaway for this codebase:** This is a direct structural analogue to `generate_song_form()`'s CFG-based song-structure generator, just one level down: the same production-rule-with-probability-weights machinery already built for song forms (`_SONG_FORMS`) could be reused almost as-is for a probabilistic melodic-phrase grammar (e.g. non-terminals for "phrase," "call," "response," terminals for scale-degree motion or rhythmic cells) as a sixth motif-generation mode, and ProCoGraM's termination-guarantee rule (every non-terminal must have a nonzero-probability path to terminals) is a concrete correctness check worth applying if this codebase's CFG song-form generator doesn't already enforce it.
