"""
genre_presets.py — loader for config/genres/*.yaml.

Collapses what used to be 6 scattered per-subgenre Python dicts (spread
across composer.py, lofi_fx.py, and drum_sampler.py, all keyed
by the same subgenre strings) into one YAML file per subgenre under
config/genres/. This module parses those files, resolves symbolic GM_*
instrument names against scripts.gm_instruments, validates the result, and
reconstructs each of the original in-memory table shapes exactly — so every
call site that used to reference a literal dict/set/frozenset now calls one
of the build_*() functions below instead, with zero behavior change.

NOTE: this module must NOT import scripts.composer at module
top level — composer.py imports *this* module (to build its
_SUBGENRE_CONFIG etc.), so a top-level import here would be circular. The
one place this module needs composer's PROGRESSIONS/
DRUM_PATTERNS (to bounds-check progression_indices/drum_pattern_indices),
the import is done lazily inside the validation function instead.
"""

from __future__ import annotations

import glob
import os

import yaml

from scripts import gm_instruments as _gm

_GENRES_DIR = os.path.join(os.path.dirname(__file__), '..', 'config', 'genres')

# Module-level cache — populated once per process by load_all().
_CACHE: dict[str, dict] | None = None


def _fail(filename: str, field: str, msg: str) -> None:
    raise ValueError(f"config/genres/{filename}: {field}: {msg}")


def _resolve_gm(value, filename: str, field: str):
    """Resolve a symbolic 'GM_*' name string against scripts.gm_instruments.
    Raises ValueError naming the offending file+field if value isn't a
    recognized GM_* name."""
    if not isinstance(value, str) or not value.startswith('GM_'):
        _fail(filename, field, f"expected a GM_* symbolic name, got {value!r}")
    if not hasattr(_gm, value):
        _fail(filename, field, f"unknown GM instrument constant {value!r}")
    return getattr(_gm, value)


def _require(doc: dict, path: str, filename: str):
    """Fetch a required (possibly-nested, dot-separated) field from doc,
    raising ValueError naming file+field if any segment is missing."""
    cur = doc
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            _fail(filename, path, "required field is missing")
        cur = cur[part]
    return cur


def _parse_one(path: str) -> tuple[str, dict]:
    filename = os.path.basename(path)
    with open(path) as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            _fail(filename, '<file>', f"invalid YAML: {e}")

    if not isinstance(raw, dict):
        _fail(filename, '<file>', "top-level YAML content must be a mapping")

    # ── required fields ─────────────────────────────────────────────────
    key = _require(raw, 'key', filename)
    _require(raw, 'composition.piano_program', filename)
    _require(raw, 'composition.bpm_range', filename)

    comp_raw = raw.get('composition')
    if not isinstance(comp_raw, dict):
        _fail(filename, 'composition', "required block is missing or not a mapping")

    for sub in ('piano_program', 'melody_program', 'countermelody_program',
                'scales', 'drum_pattern_indices', 'bpm_range',
                'progression_indices'):
        if sub not in comp_raw:
            _fail(filename, f'composition.{sub}', "required field is missing")
    if 'energy' not in comp_raw:
        # energy may legitimately be null/omitted -> None; still require the
        # key to exist so a typo'd field name doesn't silently vanish.
        comp_raw['energy'] = None

    composition = {
        'piano_program': _resolve_gm(comp_raw['piano_program'], filename, 'composition.piano_program'),
        'melody_program': _resolve_gm(comp_raw['melody_program'], filename, 'composition.melody_program'),
        'countermelody_program': _resolve_gm(comp_raw['countermelody_program'], filename, 'composition.countermelody_program'),
        'scales': list(comp_raw['scales']),
        'drum_pattern_indices': list(comp_raw['drum_pattern_indices']),
        'bpm_range': list(comp_raw['bpm_range']),
        'energy': comp_raw['energy'],
        'progression_indices': list(comp_raw['progression_indices']),
    }
    if len(composition['bpm_range']) != 2:
        _fail(filename, 'composition.bpm_range', f"expected [min, max], got {composition['bpm_range']!r}")

    doc: dict = {
        'key': key,
        'family': raw.get('family'),
        'composition': composition,
    }

    if raw.get('swing_range') is not None:
        sw = list(raw['swing_range'])
        if len(sw) != 2:
            _fail(filename, 'swing_range', f"expected [min, max], got {sw!r}")
        doc['swing_range'] = sw

    doc['cozy_bias'] = bool(raw.get('cozy_bias', False))

    # Optional single-purpose engine-feature flags, same top-level style as
    # cozy_bias above (not nested under composition/mix — each is read by
    # exactly one build_*_genres() accessor, mirroring _IR_GENRES/
    # _SIDECHAIN_DUCK_GENRES). All three are None/False unless a subgenre's
    # YAML sets them.
    doc['bass_style']   = raw.get('bass_style')      # e.g. 'glide_808'
    doc['micro_swing']  = bool(raw.get('micro_swing', False))
    doc['melody_style'] = raw.get('melody_style')    # e.g. 'continuous_arp'
    doc['roll_density'] = raw.get('roll_density')    # float 0-1+, e.g. lofi_phonk's hat-roll intensity
    doc['chh_triplet']  = bool(raw.get('chh_triplet', False))
    doc['gamaka']       = bool(raw.get('gamaka', False))
    doc['tala_overlay'] = bool(raw.get('tala_overlay', False))
    # Genre-identity controls (see config/genres/README.md).
    for field in ('bass_program', 'pad_program'):
        doc[field] = (_resolve_gm(raw[field], filename, field)
                      if raw.get(field) is not None else None)
    doc['generated_drums'] = bool(raw.get('generated_drums', False))
    doc['drums'] = bool(raw.get('drums', True))
    doc['walking_bass'] = raw.get('walking_bass')     # True/False forces it; None = sometimes
    doc['melody_density'] = raw.get('melody_density')  # 'sparse'|'medium'; None = either
    if doc['melody_density'] not in (None, 'sparse', 'medium'):
        _fail(filename, 'melody_density', "expected sparse or medium")

    tex_raw = raw.get('texture')
    if tex_raw is not None:
        if 'program' not in tex_raw or 'style' not in tex_raw:
            _fail(filename, 'texture', "block present but missing 'program' or 'style'")
        doc['texture'] = {
            'program': _resolve_gm(tex_raw['program'], filename, 'texture.program'),
            'style': tex_raw['style'],
        }

    if raw.get('drum_kit_programs') is not None:
        doc['drum_kit_programs'] = list(raw['drum_kit_programs'])

    doc['drum_sampler_pattern'] = raw.get('drum_sampler_pattern')

    mix_raw = raw.get('mix')
    if mix_raw is not None:
        for sub in ('lpf_hz', 'bitcrush_bits', 'reverb_room', 'reverb_wet',
                    'tape_wobble_depth', 'compress_ratio', 'vinyl_crackle',
                    'use_ir_reverb', 'sidechain_duck'):
            if sub not in mix_raw:
                _fail(filename, f'mix.{sub}', "required field is missing")
        doc['mix'] = dict(mix_raw)
    else:
        doc['mix'] = None

    doc['song_form'] = raw.get('song_form')

    if key != os.path.splitext(filename)[0]:
        _fail(filename, 'key', f"key {key!r} does not match filename")

    return key, doc


def _validate_bounds(parsed: dict[str, dict]) -> None:
    """Bounds-check progression_indices/drum_pattern_indices against
    composer's PROGRESSIONS/DRUM_PATTERNS tables. Imported
    lazily (not at module top level) to avoid a circular import, since
    composer.py imports this module."""
    from scripts import composer as _gmg  # lazy — see module docstring

    n_progs = len(_gmg.PROGRESSIONS)
    n_pats = len(_gmg.DRUM_PATTERNS)

    for key, doc in parsed.items():
        filename = f'{key}.yaml'
        comp = doc['composition']
        for idx in comp['progression_indices']:
            if not (0 <= idx < n_progs):
                _fail(filename, 'composition.progression_indices',
                      f"index {idx} out of range for PROGRESSIONS (len={n_progs})")
        for idx in comp['drum_pattern_indices']:
            if not (0 <= idx < n_pats):
                _fail(filename, 'composition.drum_pattern_indices',
                      f"index {idx} out of range for DRUM_PATTERNS (len={n_pats})")


def load_all() -> dict[str, dict]:
    """Parse every config/genres/*.yaml, resolve GM_* symbolic names,
    validate, and cache the result for the rest of this process's lifetime.
    Returns {subgenre_key: parsed_dict}."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    paths = sorted(glob.glob(os.path.join(_GENRES_DIR, '*.yaml')))
    if not paths:
        raise ValueError(f"no *.yaml files found under {_GENRES_DIR}")

    parsed: dict[str, dict] = {}
    for path in paths:
        key, doc = _parse_one(path)
        if key in parsed:
            _fail(os.path.basename(path), 'key', f"duplicate subgenre key {key!r}")
        parsed[key] = doc

    # Cache before bounds-checking: _validate_bounds lazily imports
    # composer, which (in the normal call order) is already
    # mid-import and simply reuses PROGRESSIONS/DRUM_PATTERNS it already
    # defined; in the reverse call order (this module imported standalone),
    # that lazy import re-enters build_*()/load_all() for this same data,
    # so the cache must already be populated to avoid infinite recursion.
    _CACHE = parsed
    try:
        _validate_bounds(parsed)
    except Exception:
        _CACHE = None
        raise

    return _CACHE


def build_subgenre_config() -> dict:
    """Exact shape of the old composer._SUBGENRE_CONFIG."""
    out = {}
    for key, doc in load_all().items():
        c = doc['composition']
        out[key] = {
            'piano': c['piano_program'],
            'melody': c['melody_program'],
            'cmelo': c['countermelody_program'],
            'scale': list(c['scales']),
            'drum_pats': list(c['drum_pattern_indices']),
            'bpm': tuple(c['bpm_range']),
            'energy': c['energy'],
            'progs': list(c['progression_indices']),
        }
    return out


def build_swing_range() -> dict:
    """Exact shape of the old composer._SWING_RANGE (only
    subgenres that had an explicit entry — no _SWING_DEFAULT fallback)."""
    out = {}
    for key, doc in load_all().items():
        if 'swing_range' in doc:
            out[key] = tuple(doc['swing_range'])
    return out


def build_cozy_subgenres() -> frozenset:
    """Exact shape of the old composer._COZY_SUBGENRES."""
    return frozenset(key for key, doc in load_all().items() if doc.get('cozy_bias'))


def build_subgenre_texture() -> dict:
    """Exact shape of the old composer._SUBGENRE_TEXTURE
    (values are (program, style) tuples, only for subgenres with a texture
    block)."""
    out = {}
    for key, doc in load_all().items():
        tex = doc.get('texture')
        if tex is not None:
            out[key] = (tex['program'], tex['style'])
    return out


def build_subgenre_drum_kits() -> dict:
    """Exact shape of the old composer._SUBGENRE_DRUM_KITS
    (only subgenres with a drum_kit_programs entry)."""
    out = {}
    for key, doc in load_all().items():
        dk = doc.get('drum_kit_programs')
        if dk is not None:
            out[key] = list(dk)
    return out


def build_genre_fx_presets() -> dict:
    """Exact shape of the old lofi_fx._GENRE_PRESETS, plus two additive
    fields from research/theory/mixing-texture.md item 8 (per-subgenre EQ
    conventions): 'presence_db' (a 3-5kHz bell/shelf cut, boom-bap-leaning
    genres only) and 'warmth_db' (a 100-200Hz boost, same genres). Both
    default to 0.0 (no-op) for any YAML that doesn't set them, so this is
    backward-compatible with every existing genre config."""
    out = {}
    for key, doc in load_all().items():
        m = doc.get('mix')
        if m is None:
            continue
        out[key] = {
            'lpf': m['lpf_hz'],
            'bits': m['bitcrush_bits'],
            'room': m['reverb_room'],
            'wet': m['reverb_wet'],
            'wobble_depth': m['tape_wobble_depth'],
            'compress_ratio': m['compress_ratio'],
            'vinyl': m['vinyl_crackle'],
            'presence_db': m.get('presence_db', 0.0),
            'warmth_db': m.get('warmth_db', 0.0),
        }
    return out


def build_ir_genres() -> set:
    """Exact shape of the old lofi_fx._IR_GENRES."""
    return {key for key, doc in load_all().items()
            if (doc.get('mix') or {}).get('use_ir_reverb')}


def build_sidechain_duck_genres() -> set:
    """Exact shape of the old lofi_fx._SIDECHAIN_DUCK_GENRES."""
    return {key for key, doc in load_all().items()
            if (doc.get('mix') or {}).get('sidechain_duck')}


def build_duck_profiles() -> dict:
    """{genre_key: 'house' | 'hiphop'} for every genre with sidechain_duck
    enabled -- research/theory/mixing-texture.md item 4: house wants an
    audible rhythmic pump (slower release, deeper duck), hip-hop wants the
    duck inaudible-as-an-effect (fast release, shallow duck). Defaults to
    'hiphop' (the more common case, and the original single hardcoded
    profile's character) if a genre opts into sidechain_duck without
    setting duck_profile explicitly."""
    return {key: (doc.get('mix') or {}).get('duck_profile', 'hiphop')
            for key, doc in load_all().items()
            if (doc.get('mix') or {}).get('sidechain_duck')}


def build_glide_808_genres() -> set:
    """Subgenres whose bass_style is 'glide_808' -- 808 pitch-slide/
    portamento bass (drill's signature technique, research/subgenres/
    lofi_drill.md). Mirrors _IR_GENRES/_SIDECHAIN_DUCK_GENRES' build
    pattern: a plain membership set built from one YAML field."""
    return {key for key, doc in load_all().items()
            if doc.get('bass_style') == 'glide_808'}


def build_roll_density() -> dict:
    """{genre_key: float} for every subgenre with a roll_density YAML field
    set -- research/theory/rhythm-groove.md: phonk's characteristic bounce
    comes from swing AND off-grid hat placement AND roll density as three
    separate levers; this is the third one, distinct from swing_range."""
    return {key: doc['roll_density'] for key, doc in load_all().items()
            if doc.get('roll_density') is not None}


def build_micro_swing_genres() -> set:
    """Subgenres with micro_swing: true -- per-voice micro-timing drum
    humanization (2-step/garage swing 'lives in the individual hits',
    research/subgenres/lofi_garage.md), instead of one uniform swing ratio."""
    return {key for key, doc in load_all().items() if doc.get('micro_swing')}


def build_chh_triplet_genres() -> set:
    """Subgenres with chh_triplet: true -- a true 12-step-per-bar
    (8th-note-triplet) hi-hat subdivision layered against the normal
    16-step kick/snare, instead of a denser 16-step hat pattern
    (research/theory/rhythm-groove.md: drill's hi-hat triplets are a
    genuinely different subdivision, not reachable by densifying the
    16-step grid). See composer.py's build_drums(chh_triplet=)."""
    return {key for key, doc in load_all().items() if doc.get('chh_triplet')}


def build_gamaka_genres() -> set:
    """Subgenres with gamaka: true -- raga-convention grace-note pitch-bend
    ornaments (bending into a note's true pitch from a fraction of a
    semitone off, then easing to center) on melody/counter-melody notes.
    research/subgenres/lofi_world.md: "the genre's most distinctive melodic
    device and the clearest way to differentiate lofi_world's melodic
    character" from other dorian-leaning genres. See composer.py's
    _gamaka_pitchbend_events() / build_melody(gamaka=)."""
    return {key for key, doc in load_all().items() if doc.get('gamaka')}


def build_tala_overlay_genres() -> set:
    """Subgenres with tala_overlay: true -- an occasional genuinely odd-meter
    (7-beat Rupak Tal, 3+2+2) polymetric overlay cycle layered over the
    existing 4/4 foundation. research/subgenres/lofi_world.md: "tala
    rhythmic cycles" alongside gamaka and drone/modal harmony. See
    composer.py's build_tala_overlay() for why this is a safe,
    fully independent overlay rather than a change to BAR/grid_tick()/
    DRUM_PATTERNS (which every other genre also depends on)."""
    return {key for key, doc in load_all().items() if doc.get('tala_overlay')}


def build_continuous_arp_genres() -> set:
    """Subgenres whose melody_style is 'continuous_arp' -- a continuous
    chord-tone arpeggiator (synthwave's melodic engine, research/subgenres/
    lofi_synthwave.md) in place of build_melody()'s phrase-based engine."""
    return {key for key, doc in load_all().items()
            if doc.get('melody_style') == 'continuous_arp'}


def build_subgenre_pat(pat_registry: dict) -> dict:
    """Exact shape of the old drum_sampler._SUBGENRE_PAT. `pat_registry`
    maps pattern name ('standard', 'boom_bap', '808_trap', 'jazz', 'dusty')
    to the actual pattern-template dict object, e.g.:
        {"standard": _PAT_STANDARD, "boom_bap": _PAT_BOOM_BAP, ...}
    Only subgenres with an explicit drum_sampler_pattern are included (rest
    fall back to a random pick at call time, same as before)."""
    out = {}
    for key, doc in load_all().items():
        name = doc.get('drum_sampler_pattern')
        if not name:
            continue
        if name not in pat_registry:
            _fail(f'{key}.yaml', 'drum_sampler_pattern',
                  f"{name!r} not found in pat_registry {sorted(pat_registry)}")
        out[key] = pat_registry[name]
    return out


def build_form_overrides() -> dict:
    """Exact shape of the old composer._FORM_BY_SUBGENRE
    (only subgenres with an explicit song_form)."""
    out = {}
    for key, doc in load_all().items():
        form = doc.get('song_form')
        if form:
            out[key] = form
    return out


def build_bass_programs() -> dict:
    return {k: d['bass_program'] for k, d in load_all().items() if d.get('bass_program') is not None}


def build_pad_programs() -> dict:
    return {k: d['pad_program'] for k, d in load_all().items() if d.get('pad_program') is not None}


def build_generated_drum_genres() -> set:
    """Genres whose drums may be replaced by Euclidean/CA/polyrhythm patterns.
    Everything else keeps its curated, genre-defining grooves."""
    return {k for k, d in load_all().items() if d.get('generated_drums')}


def build_beatless_genres() -> set:
    return {k for k, d in load_all().items() if not d.get('drums', True)}


def build_walking_bass() -> dict:
    return {k: bool(d['walking_bass']) for k, d in load_all().items()
            if d.get('walking_bass') is not None}


def build_melody_density() -> dict:
    return {k: d['melody_density'] for k, d in load_all().items() if d.get('melody_density')}
