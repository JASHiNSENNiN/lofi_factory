# lofibot (cyu2019)

**One-line:** A Node.js + Python webapp that ingests a short 2- or 4-measure 4/4 sample loop and algorithmically stretches/processes it into a full lofi hip-hop track.

**Description:** Built for MLH Local Hack Day, lofibot takes a user-supplied loop (named `loop_bpm_numMeasures.wav`) via either a web UI or CLI (`python script.py filename bpm number_of_measures`) and produces a lofi-styled song from it. It leans on `librosa` for audio analysis and `pydub`/FFmpeg for manipulation rather than symbolic/MIDI composition — it's sample-remixing, not generative composition from scratch.

**Core algorithm/technique:** Not explicitly documented in the README; based on the dependency set (librosa for feature extraction/tempo-beat tracking, pydub for segment manipulation), the likely approach is beat-slicing/time-stretching the input loop and layering lofi-style processing (bitcrush/filtering/effects) rather than any note-level generative algorithm.

**License:** Unspecified/none found.

**URL:** [https://github.com/cyu2019/lofibot](https://github.com/cyu2019/lofibot)

**Takeaway for this codebase:** This project confirms that a viable, CPU-cheap lofi pipeline can lean on sample manipulation (librosa beat-tracking + pydub layering) rather than symbolic generation — useful as a sanity check that this repo's approach (fully symbolic music21/harmony-engine composition plus `lofi_fx.py`'s offline mix chain) is heavier-weight but more controllable than pure sample-remix tools; not much new to steal algorithmically, but worth noting as the "low-effort" end of the design space this project intentionally goes beyond.
