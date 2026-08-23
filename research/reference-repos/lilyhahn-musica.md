# musica (lilyhahn)

**One-line:** A C++ cellular-automaton music/art generator built on Rule 30, rendering both PNG visualizations of the automaton and piano-sample-based audio driven by its evolution.

**Description:** Musica runs Wolfram's Rule 30 (using LibGD for automaton-to-PNG rendering) and separately maps the same automaton state evolution to rhythm and melody using real piano samples from the University of Iowa Musical Instrument Sample database, played back via the irrKlang audio library. The README candidly self-describes results as "somewhat ok music," and the repo has modest activity (6 stars, 1 fork, 18 commits) — useful as evidence of the genre's difficulty rather than a polished reference implementation.

**Core algorithm/technique:** Wolfram elementary cellular automaton Rule 30, single-rule-driving-both-rhythm-and-melody, rendered with real sampled piano audio.

**License:** GPL-2.0.

**URL:** [https://github.com/lilyhahn/musica](https://github.com/lilyhahn/musica)

**Takeaway for this codebase:** Directly cross-checks the existing rule-30/90/110/184 CA implementation (`_ca_step`/`_ca_evolve`) in `scripts/generate_music_gemini.py`: this project confirms Rule 30 alone tends toward chaotic/noisy results when used for melody (matching Wolfram's own classification of Rule 30 as Class III/chaotic), reinforcing that this codebase's choice to also offer Rule 90 (fractal/Sierpinski, more musically structured) and Rule 110 (Class IV, edge-of-chaos, typically the most musically interesting) alongside Rule 30 is the right call — if extending the CA system, prioritize surfacing Rule 110 patterns for melody/lead lines and reserve Rule 30/184 for percussion/texture where their chaotic or particle-like (184, traffic-rule) behavior is less harmonically exposed.
