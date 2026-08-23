# markov-music (kstar)

**One-line:** An educational Markov-chain music generator trained on Bach's violin concertos, built as a teaching demo on stochastic processes for physics undergraduates.

**Description:** The pipeline is explicit and staged: MIDI files are converted to unigrams (individual notes), unigrams are aggregated into n-grams (note sequences of order n), an n-gram transition/probability model is built from those, and new sequences are sampled from the model and resynthesized back to MIDI with adjustable tempo, instrumentation, and transposition at resynthesis time. Sample precomputed data files (`digrams.dat`, `unigrams.dat`) ship in the repo so the model doesn't need to be rebuilt from scratch to demo it.

**Core algorithm/technique:** Variable-order n-gram Markov chain (staged unigram → n-gram → transition-matrix pipeline) over MIDI note sequences.

**License:** Unspecified/none found.

**URL:** [https://github.com/kstar/markov-music](https://github.com/kstar/markov-music)

**Takeaway for this codebase:** The explicit "unigram → n-gram → transition matrix" staging (rather than building the full n-gram model in one pass) is a clean pattern for making Markov order (1st vs. 2nd vs. 3rd-order) a tunable parameter — if a Markov-based melody mode gets added here, exposing chain order as a config knob (like the existing rule-30/90/110/184 CA rule selection is exposed) would let higher-order chains trade off more idiomatic phrasing against more sparse/overfit-to-source transition tables, worth testing against the corpus that would feed `harmony_engine.py`.
