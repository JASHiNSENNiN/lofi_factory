# Mixing texture — refinements beyond the current `lofi_fx.py` chain

This is a follow-on to the already-implemented Pedalboard chain (`scripts/lofi_fx.py`):
bitcrush/resample grit → hand-rolled tape wow/flutter → lowpass/reverb tail →
optional GSM/IR/sidechain layers → sub-bass saturation → vinyl crackle → per-track
LUFS mastering. The goal here isn't to re-describe that chain but to find real
parameter anchors and techniques that aren't in it yet.

## 1. Tape wow & flutter: real-world numbers to anchor the model

The current implementation maps `wobble_depth` to a 0.5–3.5ms delay-line
modulation with wow at 0.6–1.4Hz and flutter at 5–9Hz, blended 65/35
wow-dominant. That's structurally sound (variable-delay line is *the* standard
technique), but the depth range isn't anchored to any real spec. Actual
consumer/pro tape gear is measured in **%WRMS** (weighted RMS speed deviation,
per DIN/NAB/CCIR/JIS standards): hi-fi cassette decks spec at ≤±0.2% WRMS,
non-hi-fi cassette machines ≤±0.4%, a studio-grade reel-to-reel like an Otari
MX5050-III-2 at 15 ips comes in around 0.09%, and consumer reel-to-reel decks
from the 60s/70s sit around 0.25% at 7.5 ips ([Tapeheads.net wow/flutter
audibility thread](https://www.tapeheads.net/threads/minimum-wow-and-flutter-percentage-that-is-audible.58862/),
[wow & flutter explainer](https://reflectiveobserver.medium.com/wow-flutter-explained-31cc9495d24),
[Wow and flutter measurement — Wikipedia](https://en.wikipedia.org/wiki/Wow_and_flutter_measurement)).
%WRMS translates to peak pitch deviation roughly 2-3x the RMS figure, so a
"gritty consumer cassette" character (~0.3-0.4% WRMS) corresponds to peak
speed deviation around 0.8-1.2%, which at typical musical pitch is in the same
ballpark the code already targets — but the mapping is currently a flat
depth-to-ms curve rather than tied to any measured spec, so there's no
documented reasoning for *why* 0.5-3.5ms was chosen over, say, 0.3-2.0ms.

A second, currently-missing real-tape phenomenon: **head bump**, a low-frequency
resonant boost (typically 3dB or more around 50-70Hz, with the exact center
frequency set by tape speed and head gap geometry — 7.5 ips deep in the low
end, 15 ips higher, 30 ips higher still) caused by the playback head's pole-piece
geometry interacting with wavelengths near the gap length
([Tapeheads.net head bump thread](https://www.tapeheads.net/threads/low-frequency-head-bumps.30781/),
[Gearspace: what causes tape head bump](https://gearspace.com/board/geekzone/588930-what-causes-tape-head-bump.html)).
This is a static frequency-response coloration, not a time-varying modulation —
i.e., a different effect than wow/flutter, implementable as a simple resonant
low-shelf/peak boost around 50-70Hz, independent of the delay-line code.

## 2. Vinyl crackle: physical modeling vs. the current sparse-impulse approach

`_make_crackle` uses sparse randomly-placed impulse "pops" plus one-pole
lowpassed noise — a reasonable, cheap approximation. More sophisticated
commercial approaches (e.g. Minta Foundry's **Needlepoint**) physically model
a rotating virtual platter with per-revolution dust/scratch placement rather
than looping fixed noise, giving crackle grain sizes, density, and per-category
volume controls, and ensuring pops repeat with the record's rotation period
rather than being purely random ([Needlepoint plugin](https://www.mintafoundry.com/patina),
via [PluginErds physical modeling roundup](https://pluginerds.com/11-physical-modelling-plugins/)).
Academic gramophone-noise synthesis work builds crackle from three additive
layers: parametric-EQ-filtered white noise for the hiss floor, sparse
low-frequency pulses for deep scratches, and extra-lowpassed noise for rumble
([arXiv: Realistic Gramophone Noise Synthesis using a Diffusion Model](https://arxiv.org/pdf/2206.06259)).
That three-layer decomposition (hiss / pop / rumble, each independently
shaped) is a concrete, cheap refinement over the current single noise-plus-pops
approach — the code already has the pop layer and a crude hiss layer via the
one-pole filter, but has no separate rumble layer (sub-40Hz lowpassed noise
tracking turntable wow), which would pair naturally with the existing sub-bass
saturation stage.

## 3. Bitcrush/lo-fi degradation: beyond flat bit-depth reduction

The existing bitcrush presets already reference MPC2000/S950-style bit depths
in comments. Real hardware specifics worth encoding: the E-mu SP-1200 runs
12-bit/26.04kHz and its characteristic "dirt" comes less from the bit depth
itself than from its **A/D and D/A converter nonlinearity and crude pitch
interpolation artifacts** when samples are pitched down after being recorded
pitched-up (the classic "sample at 45/78 RPM, tune back down" trick), while
the Akai S950 is prized for its **analog 6th-order Butterworth anti-aliasing
lowpass filter**, a specific, steep, resonant-ish rolloff shape rather than a
generic digital LPF ([MusicTech: wavetracing SP-1200/S950 filter](https://musictech.com/news/wavetracing-sp950-e-mu-sp1200-akai-s950/),
[Gearspace: SP-1200 filtering discussion](https://gearspace.com/board/electronic-music-instruments-and-electronic-music-production/628756-what-kind-filtering-done-sp1200-recreating-12-bit-akai-possible.html)).
The current chain's `Resample(target_sample_rate=sr_target)` + `Bitcrush`
combo captures the aliasing-on-downsample character reasonably well but uses
Pedalboard's generic LowpassFilter for the post-crush tone shaping rather than
a steeper filter order that would read as more "S950-like." Separately: proper
bit-depth reduction should dither before truncating — adding low-level noise
before quantization decorrelates the quantization error from the signal,
avoiding harsh/tonal digital artifacts, and *shaped* dither pushes the added
noise toward frequencies the ear is less sensitive to
([iZotope: what is dithering](https://www.izotope.com/en/learn/what-is-dithering-in-audio.html),
[Sage Audio: what is noise shaping](https://www.sageaudio.com/blog/mastering/what-is-noise-shaping.php)).
Pedalboard's `Bitcrush` plugin does not document doing this internally — worth
verifying, since undithered bitcrushing is where "harsh/digital" (vs.
"vintage/musical") crush character comes from.

## 4. Sidechain ducking: genre-authentic parameter ranges

Current `_apply_kick_sidechain_duck` uses attack 6ms / release 180ms / duck
depth 4dB — reasonable, but here's what genre convention actually calls for.
**House/EDM** pumping uses fast attack, fast-to-moderate release, and ratios
commonly 4:1 up to as extreme as 12:1 at low (-45dB) thresholds for an
obvious, rhythmic pump, often timed to a quarter note
([EDMProd sidechain guide](https://www.edmprod.com/sidechain-compression/)).
**Hip-hop**, by contrast, wants the duck *inaudible as an effect* — attack
2-5ms, release a much shorter 40-80ms, ratio a gentler 3:1-5:1 — the goal is
punch/separation between kick and bass, not an audible pump
([Mastering.com sidechain guide](https://mastering.com/sidechain-compression-guide/)).
This maps cleanly onto the existing `_SIDECHAIN_DUCK_GENRES` set: `lofi_house`
genuinely wants pump character (slower release, deeper duck), while
`hip_hop_lofi`/`chillhop`/`lofi_drill` want the current fast-attack/
short-ish-release approach already coded — the gap is that all five genres in
that set currently share one hardcoded `_DUCK_RELEASE_MS = 180.0` /
`_DUCK_AMOUNT_DB = 4.0`, with no house-vs-hiphop split.

## 5. Convolution reverb: genre-appropriate IR selection and more free sources

Beyond Voxengo's pack (already in use), free/permissively-licensed IR
libraries worth knowing about: **OpenAir** (University of York's public IR
archive, various spaces including real acoustic halls and unusual objects),
**MConvolutionEZ**'s bundled library (halls/chambers/plates/rooms, free
plugin), and **Convology XT**'s 70 IRs captured from vintage hardware reverb
units rather than pure acoustic spaces
([Production Expert free-IR roundup](https://www.production-expert.com/production-expert-1/free-convolution-reverbs-tools-amp-impulse-responses-for-music-and-post),
[Bedroom Producers Blog: free convolution VSTs](https://bedroomproducersblog.com/2019/03/18/free-convolution-reverb-vst/)).
Vintage-hardware-unit IRs (plates, springs) are a genuinely different texture
from room IRs and could suit boom-bap/hip-hop-lofi genres (which historically
reference SP-1200-era hardware reverb units) better than the current
salon/hall/room set, which is tuned for the jazz/piano/acoustic genres it's
already gated to.

## 6. Tape saturation: a genuinely distinct effect from the existing sub-bass tanh stage

`_apply_sub_bass_saturation` already does band-limited tanh saturation, but
only below 150Hz. Full-band **tape saturation** is a musically different
effect: tape's magnetic hysteresis behaves as a broadly *symmetric* soft
clipper (tanh-like), producing mostly **odd harmonics** (3rd, 5th, 7th) that
read as warmth/presence rather than "buzz," in contrast to **tube saturation**,
which is asymmetric (piecewise/biased waveshaping) and produces even harmonics
too ([Kern Audio: tube/tape/transformer saturation](https://kernaudio.io/guides/saturation/tube-tape-transformer),
[Kern Audio: harmonic distortion explained](https://kernaudio.io/guides/saturation/harmonic-distortion-explained),
[UAudio: guide to distortion for home recordists](https://www.uaudio.com/blogs/ua/a-guide-to-distortion-for-home-recordists)).
A dedicated `_apply_tape_saturation` applied full-band (not just sub-150Hz)
using the same tanh-drive pattern already proven in the sub-bass function
would be a natural, low-risk addition — distinct in *scope* (full spectrum)
even though the underlying math (tanh waveshaping) is the same family. One
digital-modeling caveat worth carrying into any implementation: full-band
waveshaping risks generating harmonics above Nyquist that alias back as
inharmonic noise unless oversampled first — a real risk the current sub-bass
function mostly dodges by only driving already-lowpassed content.

## 7. LUFS conventions: is -17 right for background-listening lofi?

The existing `_TRACK_LUFS_TARGET = -17.0` is justified in-code purely by
avoiding double-normalization with the video-level `-14` LUFS pass — a sound
technical reason, but the research doesn't show a genre-specific "lofi radio"
LUFS convention distinct from generic streaming targets. What it does show:
the -14 LUFS figure is a **platform normalization target, not a mastering
mandate** — tracks aren't supposed to be authored at exactly -14, the platform
turns louder/quieter masters down/up to match it, and genre should still drive
the actual mastering level (hip-hop/EDM/pop often master hot, -10 to -8 LUFS,
letting the platform pull them down)
([MixingLessons: LUFS and why it's not -14](https://www.mixinglessons.com/lufs-loudness-unit-full-scale/),
[Mat Leffler-Schulman: streaming LUFS targets 2026](https://matlefflerschulman.com/mastering-articles/loudness-targets-and-mastering-for-streaming-platforms)).
Since lofi is explicitly background/ambient listening (low dynamic contrast,
low LRA desired, not a "hit hard" genre), -17 per-track before a second -14
pass is defensible and arguably *more* genre-appropriate than chasing -14
directly — no source found suggests lofi should be mastered loud. The one
concrete thing worth adding: LRA (loudness range) targeting isn't in the
current chain at all — `assemble_video.py`'s ffmpeg pass sets `LRA=11`, but
nothing constrains per-track dynamic range before that.

## 8. Per-subgenre EQ/saturation conventions

Documented producer convention (not academic, but consistent across sources)
draws a real boom-bap-vs-ambient-lofi split: **boom-bap** wants a gentle
high-shelf rolloff above ~12kHz, a small +100-200Hz warmth boost, and a 1-2dB
cut around 3-5kHz to tame digital harshness, plus saturation mixed at a
noticeable 10-20% wet for audible tape/analog character; **ambient/piano
lofi** wants a gentler low-end rolloff below 60-80Hz (removing rumble rather
than adding warmth) and a similar high rolloff around 10-15kHz to simulate
"damaged vinyl," with lighter, subtler saturation
([12bitsoul: how to make lofi beats that sound good](https://www.12bitsoul.com/blogs/news/how-to-make-lo-fi-beats-that-actually-sound-good),
[HitProducerStash: EQ frequency cheatsheet for beats](https://www.hitproducerstash.com/blog/eq-frequency-cheatsheet-beats)).
This maps directly onto the existing `_GENRE_PRESETS` table's `lpf`/`bits`
spread (dark/hip-hop genres already sit lower-LPF/lower-bits than
piano/classical genres, which is the right direction) but there's no explicit
3-5kHz presence dip or 100-200Hz warmth-boost parameter in the current preset
schema at all — the chain only has one broadband `LowpassFilter` per genre,
no midrange shelf/bell control.

## Concrete additions

| table/function to extend | proposed entries | rationale |
|---|---|---|
| `_apply_wow_flutter` / `_WOW_HZ_RANGE`, depth mapping | Anchor `depth_ms` curve to measured %WRMS bands (e.g. "clean" preset ≈0.1-0.15% WRMS-equivalent, "gritty consumer cassette" ≈0.3-0.4%) instead of an unanchored 0.5-3.5ms constant | Gives the existing depth mapping a documented real-world basis instead of an arbitrary range; low-risk, same code path |
| new `_apply_head_bump` (or fold into `board_post`'s LowpassFilter stage as a resonant low-shelf) | +2 to +4dB peak/shelf around 50-70Hz, tunable by an implied "tape speed" the genre preset already implies via `wobble_depth` | Real, currently-missing static tape-EQ coloration distinct from the time-varying wow/flutter effect already implemented |
| `_make_crackle` | Split into 3 additive layers: hiss (existing lowpassed noise), pops (existing sparse impulses), and a new sub-40Hz lowpassed rumble layer scaled with `vinyl_vol` | Matches documented 3-layer gramophone-noise-synthesis decomposition (hiss/pop/rumble); rumble layer pairs naturally with the existing `_apply_sub_bass_saturation` band |
| new `_apply_tape_saturation` | Full-band tanh waveshaper, drive ~6-10dB (gentler than `_SUB_BASS_DRIVE_DB`'s 14dB since it's full-spectrum not band-limited), mixed 10-20% wet per boom-bap-leaning genres, lighter (~5-10%) for ambient/piano genres | Genuinely distinct in *scope* from the existing sub-bass-only saturation; documented tape/tube saturation curve distinction (symmetric/odd-harmonic vs asymmetric/even-harmonic) justifies keeping it tanh-based like the sub-bass stage rather than switching models |
| `_SIDECHAIN_DUCK_GENRES` / duck params | Split into two duck presets: "house pump" (attack ~2ms, release ~150-250ms, duck 5-6dB) for `lofi_house`, vs "hip-hop punch" (attack ~2-5ms, release ~40-80ms, duck 2-3dB) for `hip_hop_lofi`/`chillhop`/`lo_fi_funk`/`lofi_drill` | Documented genre convention shows house wants an audible rhythmic pump while hip-hop wants an inaudible punch-enhancing duck — current code applies one duck profile to both, per source guidance these should differ |
| `_GENRE_PRESETS` (new fields) | Add `presence_db` (a 3-5kHz bell/shelf cut, ~-1 to -2dB for boom-bap/hip-hop genres, ~0dB for ambient) and `warmth_db` (a 100-200Hz boost, +1 to +2dB for boom-bap, ~0dB for piano/classical) | Documented boom-bap vs ambient EQ convention isn't representable in the current schema (only one broadband LPF); these two additive Pedalboard `PeakFilter`/shelf stages would close that gap cheaply |
| `_IR_DIR` / `_IR_GENRES` asset additions | Add 1-2 vintage-hardware-reverb IRs (plate/spring character, e.g. from Convology XT's free set) alongside the existing room/hall/chamber IRs, and gate them toward boom-bap/hip-hop-lofi genres rather than only jazz/piano | Hardware plate/spring reverb is the historically-correct reference texture for boom-bap/SP-1200-era production, distinct from the acoustic-room character the current IR set (jazz/piano-gated) already covers well |
