# L-System-Music-Module (ephemeralwaves)

**One-line:** An npm module that generates monophonic melodies from an L-system grammar, mapping the classic Koch-curve production rule (`F → F+F-F-F+F`) onto pitch movement within a pentatonic scale.

**Description:** Adapted from the "Fractal-Music-Generator" MuseScore 2.0 plugin, the module exposes a `Lindenmayer` class (grammar computation: axiom, production rules, iteration depth) and a `Melody` class (turns the resulting symbol string into notes). `F` symbols emit a note, `+`/`-` symbols step up/down within the C pentatonic scale starting at C4; the computed string is walked once to produce a MIDI-exportable melody. It's a very small, focused implementation (JS/npm, not Python) but the algorithm is trivially portable.

**Core algorithm/technique:** Deterministic L-system string rewriting (turtle-graphics-style interpretation borrowed from fractal curve drawing) mapped to scale-degree steps instead of turtle angles.

**License:** GPL-3.0.

**URL:** [https://github.com/ephemeralwaves/L-System-Music-Module](https://github.com/ephemeralwaves/L-System-Music-Module)

**Takeaway for this codebase:** This is the clearest concrete "new algorithm to add" from the whole survey: this codebase has Euclidean and CA rhythm generators and a CFG-based song-form generator, but no melodic L-system — porting the Koch-curve-style production rule (or a custom one) into Python as a fifth motif-generation mode is cheap (pure string rewriting + scale-degree walk, no dependencies) and would give genuinely fractal/self-similar melodic contours as an alternative to `generate_motif`'s current approach; scale-constraining the walk (as this module does with C pentatonic) is the key trick to keep L-system output harmonically usable rather than atonal-random.
