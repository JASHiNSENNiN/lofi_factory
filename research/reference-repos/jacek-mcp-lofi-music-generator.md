# LoFi-music-generator (jacek-mcp)

**One-line:** An open-source university (UPC) project generating lofi hip-hop with two separate RNNs — one for melody, one for chords — trained on 300 MIDI files (~32 hours, 110,630 notes, 28 lofi chord patterns).

**Description:** The system predicts melody and harmony independently via two RNNs rather than a single joint model, and evaluated three note-embedding strategies (single combined vocabulary, dual, and triple separate embeddings for note/duration/velocity), finding triple embeddings produced less-overfit, more original output. Generated MIDI is rendered to audio via FluidSynth with custom SoundFont (SF2) instruments, then post-processed with additional WAV effects layers.

**Core algorithm/technique:** Two independent sequence-prediction RNNs (melody, chords) with learned embeddings over note/duration/velocity tokens; deep-learning, trained on a curated lofi MIDI corpus.

**License:** Unspecified/none found.

**URL:** [https://github.com/jacek-mcp/LoFi-music-generator](https://github.com/jacek-mcp/LoFi-music-generator)

**Reference only, not implementable** — this project runs on a GPU-less i3-7100U laptop CPU; the RNN training pipeline (300 MIDI files, dual-network sequence models) is not portable to this environment.

**Takeaway for this codebase:** The one transferable idea is the embedding/tokenization lesson, reframed for a rule-based system: separating "what varies" (pitch vs. duration vs. velocity) into independently-controllable axes reduced overfitting/staleness for them, which maps to `generate_motif`/`vary_motif` in this codebase — consider varying pitch-contour, rhythm, and velocity/dynamics as three independently-perturbable axes in `vary_motif` rather than one combined mutation, to get more varied-but-coherent motif variations without adding any ML.
