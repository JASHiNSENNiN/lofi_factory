---
subgenre_key: lofi_world
status: existing
bpm_range: [68, 84]              # current code: (70, 86). General lofi tempo convention (65-95, "sweet spot" 70-80) applies since sources found no world-fusion-specific tempo deviation from base lofi norms — the genre's distinctiveness is timbral/modal, not tempo-driven. Recommend a marginal downward nudge (68-84 vs 70-86) simply to keep it centered in the same core lofi pocket as its closest sibling (bossa_lofi: 74-88) rather than running slightly hotter; a minor tuning note, not a strong correction.
swing_range: [0.56, 0.66]        # matches current code (0.58, 0.68) closely, trimmed slightly. Sources confirm standard lofi swing convention (10-15% quantization) applies, with tala-cycle-based grooves (Teental/Rupak/Adi) providing rhythmic interest through meter/pattern rather than heavier swing — recommend a marginally tighter band than the current one so lofi_world doesn't read as swung as hip_hop_lofi/nujabes, since its rhythmic distinctiveness should come from the ethnic-percussion texture layer, not swing depth.
scales: [dorian, phrygian_dominant, natural_minor, pentatonic_minor]
mood_descriptors: [exotic, meditative, hybrid, earthy, transportive]
---

## Harmony
World-fusion sources are explicit that harmony should stay minimal and modal to avoid clashing with the borrowed melodic material: "start melodically with drone and modal bass, introducing chords sparingly to preserve raga/maqam color, favoring modal harmony like sus/add9 and quartal voicings... that avoid clashing with restricted notes." This is a meaningfully different harmonic philosophy from the rest of the roster's jazz-7th/9th default — lofi_world should favor sparser, more static harmonic beds (a held drone or simple sus/add9 vamp) rather than the ii-V-I jazz turnarounds appropriate to lofi_jazz or jazz_cafe, letting the phrygian_dominant/Hijaz-maqam melodic color do the expressive work instead of chord movement.

## Melody
Sitar (lead) and koto (counter-melody) — already the code's chosen GM voices — should carry maqam-like modal phrases (Hijaz/Phrygian dominant, evoking the flamenco/Middle Eastern/Turkish "distinctive flavor" sources describe) rather than Western jazz-improv phrasing; muting techniques on sitar strings for "staccato-like effects" is a cited idiomatic ornament technique worth reflecting in articulation/velocity choices. Gamaka-style ornamentation (grace-note bends around a target pitch, per raga convention) is the genre's most distinctive melodic device and the clearest way to differentiate lofi_world's melodic character from dorian-based chillhop/nujabes even when they share the dorian scale option.

## Rhythm/groove
World-fusion percussion should draw on tala-cycle-inspired meter/pattern variety (e.g. Teental 16, Rupak 7, Adi 8 as named reference cycles) layered with the kit's drum-pattern system for a hybrid feel, rather than treating percussion as generic boom-bap — this is lofi_world's clearest rhythmic-identity opportunity versus the rest of the roster, though full odd-meter implementation would exceed the current 4/4-only engine (flagged as a "needs new feature" note below). Within 4/4 constraints, favor the kalimba/hand-percussion-adjacent texture layer over a standard trap-hat pattern for the most idiomatic result achievable with existing code.

## Arrangement/structure
Layering approach should mirror world-fusion's cross-cultural "hybrid ensemble" convention — sources describe combining, e.g., "Middle Eastern strings with West African rhythms" or "Japanese woodwinds over Andean percussion" as a legitimate compositional strategy, which validates the code's existing sitar+koto+kalimba combination (South Asian lead, East Asian counter-melody, African-adjacent texture) as an intentional pan-cultural blend rather than a single-tradition pastiche — arrangement should keep these three timbres clearly distinguishable in the mix (different registers/roles) rather than blurred together.

## Reference repos/algorithms
No dedicated world-fusion-lofi algorithmic generator repos found; the clearest theoretical grounding is raga/maqam pedagogical material (drone+modal-bass harmonic approach, gamaka ornamentation, tala rhythmic cycles) rather than any existing MIDI-generation codebase. Commercial "Ethnic" Kontakt/VST libraries (sitar, koto, kalimba, oud, kora, tabla, duduk, frame-drum sample sets) confirm this instrumentation combination as an established production convention worth treating as a durable reference point even without open-source code to draw on directly.

## Provenance
- [Indian Fusion - Melodigging](https://www.melodigging.com/genre/indian-fusion)
- ["Strings Beyond Borders: Adapting Sitar Techniques for Modern Fusion Music"](https://www.octavesonline.com/post/strings-beyond-borders-adapting-sitar-techniques-for-modern-fusion-music)
- [World Fusion - Melodigging](https://www.melodigging.com/genre/world-fusion)
- [Phrygian dominant scale — Wikipedia](https://en.wikipedia.org/wiki/Phrygian_dominant_scale)
- [9 Best Ethnic, Traditional & Regional Kontakt Libraries](https://pluginerds.com/9-best-ethnic-kontakt-libraries/)
- [Lofi Hip Hop Guide: Origins, Styles, Artists, Hits & Impact - OurMusicWorld.com](https://www.ourmusicworld.com/archives/10229)
