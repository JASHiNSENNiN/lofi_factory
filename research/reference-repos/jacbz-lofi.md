# Lofi (jacbz)

**One-line:** An ML-supported lofi generator: a PyTorch VAE encodes lofi tracks into a 100-dimensional latent feature vector, and a Tone.js web client synthesizes playable audio from sampled/interpolated vectors.

**Description:** Trained on a synthesized dataset combining Hooktheory (chord/melody) and Spotify audio-feature data, the VAE learns a compact latent space representing harmony, melody, and other lofi-aesthetic parameters. A Flask REST API serves the trained checkpoint so the TypeScript/Webpack web client can request new latent vectors and render them client-side via Tone.js, without needing to retrain locally.

**Core algorithm/technique:** Variational Autoencoder (VAE) latent-space music generation; deep learning, requires PyTorch training (though inference from a pretrained checkpoint is lighter-weight than training).

**License:** Apache License (per repo badge).

**URL:** [https://github.com/jacbz/Lofi](https://github.com/jacbz/Lofi)

**Reference only, not implementable** — this project runs on a GPU-less i3-7100U laptop CPU; VAE training against a Hooktheory+Spotify dataset is out of scope, though CPU-only inference from a small pretrained checkpoint could theoretically run (untested, not recommended given project constraints).

**Takeaway for this codebase:** The conceptual takeaway, not the ML: collapsing "what makes a track sound lofi" into a small number of tunable axes (their 100-dim vector) is basically what a well-designed parameter surface for `lofi_fx.py` should aim for — e.g. exposing a handful of named "vibe" knobs (wow/flutter depth, bitcrush amount, crackle density, sidechain depth) that map to coordinated multi-parameter presets, rather than requiring manual tuning of every individual effect parameter per track.
