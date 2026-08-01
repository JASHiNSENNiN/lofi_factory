"""
Musical DNA extraction: take a mainstream song and derive lofi MIDI generation parameters.

Paths, tried in order — procedural/deterministic paths first, LLM last and opt-in only:
  A) MIDI file scrape from bitmidi.com → parse melody/chords → map to params
  B) Spotify audio features → deterministic parameter mapping
  C) Text-heuristic: keyword-lexicon mood/energy inference from title+artist, deterministic
     (same song -> same params every run), no network call, no LLM. This is the primary
     fallback and does the job Groq used to do, without an API call.
  D) Groq LLM derivation — explicit opt-in failsafe only (LOFI_LLM_FAILSAFE=1 env var),
     tried only if C somehow raises. Should essentially never be reached.
  E) Absolute last-resort deterministic hash fallback (no text analysis at all).

Output: MidiDNA — maps 1:1 to the `params` dict that build_midi() reads.
"""

from __future__ import annotations

import hashlib
import io
import os
import random
import re
import time
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .models import MidiDNA, SongInfo, SpotifyFeatures

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

# Keys available in generate_music_gemini.KEY_ROOTS
_VALID_KEYS = ["Am", "Dm", "Em", "Gm", "Cm", "C", "G", "F"]

# Pitch class semitone from C for each key root (for distance calculations)
# Am=9, Dm=2, Em=4, Gm=7, Cm=0, C=0, G=7, F=5
_KEY_SEMITONES: dict[str, int] = {
    "Am": 9, "Dm": 2, "Em": 4, "Gm": 7, "Cm": 0, "C": 0, "G": 7, "F": 5
}

# Subgenres available in generate_music_gemini._SUBGENRE_CONFIG
_VALID_SUBGENRES = [
    "chillhop", "lofi_jazz", "dark_lofi", "bossa_lofi", "neo_soul", "ambient",
    "nujabes", "city_pop", "lofi_phonk", "morning_lofi", "hip_hop_lofi", "chill_beats",
    "cozy_cafe", "anime_lofi", "summer_vibes", "study_lofi", "jazz_cafe", "piano_lofi",
    "lo_fi_funk", "bedroom_pop", "lofi_rnb", "lofi_classical", "lofi_house", "vaporwave",
]

# Progression index groups by character
_MINOR_PROGS = [0, 1, 3, 6, 7, 10, 11, 13, 14, 15]
_MAJOR_PROGS = [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 28, 29]
_JAZZ_PROGS  = [2, 5, 8, 9, 26, 27, 30]

# Scale templates for Hamming-distance detection from MIDI pitch classes
_SCALE_TEMPLATES: dict[str, list[int]] = {
    "pent":       [0, 3, 5, 7, 10],
    "major_pent": [0, 2, 4, 7, 9],
    "dorian":     [0, 2, 3, 5, 7, 9, 10],
    "major":      [0, 2, 4, 5, 7, 9, 11],
    "lydian":     [0, 2, 4, 6, 7, 9, 11],
    "mixo":       [0, 2, 4, 5, 7, 9, 10],
    "phryg":      [0, 1, 3, 5, 7, 8, 10],
}

# Mood phrases by valence/energy quadrant
_MOOD_PHRASES: dict[str, list[str]] = {
    "bright_high":  [
        "the kind of song you play with the windows down",
        "a summer afternoon that never quite ends",
        "golden hour on repeat",
    ],
    "bright_low":   [
        "soft morning light, everything settling into place",
        "the world is good and quiet right now",
        "warm coffee and no particular place to be",
    ],
    "dark_high":    [
        "running from something that isn't there anymore",
        "4am and the city hums a song you almost know",
        "the feeling right before something changes",
    ],
    "dark_low":     [
        "3am and the world is a quiet, heavy thing",
        "lofi for when the silence gets too loud",
        "the rain doesn't ask you anything",
    ],
}

_BITMIDI_SEARCH = "https://bitmidi.com/search"
_BITMIDI_RATE_S = 2.0  # seconds between requests (polite scraping)
_last_bitmidi_req = 0.0


# ─── Public API ────────────────────────────────────────────────────────────────

def extract_song_dna(song: "SongInfo", spotify_features: "SpotifyFeatures | None") -> "MidiDNA":
    """
    Derive MidiDNA for a song. Tries procedural paths in order; always returns a result.
    Groq is opt-in (LOFI_LLM_FAILSAFE=1) and only reached if every procedural path fails.
    """
    from .models import MidiDNA

    # Path A: MIDI file scrape
    try:
        midi_bytes = _download_bitmidi(song.artist, song.title)
        if midi_bytes:
            parsed = _parse_midi_bytes(midi_bytes)
            dna = _build_dna_from_midi_parse(song, parsed)
            print(f"  [extract] MIDI parse succeeded for '{song.title}'")
            return dna
    except Exception as e:
        print(f"  [extract] MIDI parse failed: {e}")

    # Path B: Spotify audio features
    if spotify_features is not None:
        try:
            dna = _derive_dna_from_spotify(song, spotify_features)
            print(f"  [extract] Spotify features used for '{song.title}'")
            return dna
        except Exception as e:
            print(f"  [extract] Spotify feature mapping failed: {e}")

    # Path C: text-heuristic — deterministic, keyword-lexicon derived from title+artist.
    # This is the primary fallback and replaces what Groq used to be relied on for.
    try:
        dna = _derive_dna_from_heuristic(song)
        print(f"  [extract] Text-heuristic derivation used for '{song.title}'")
        return dna
    except Exception as e:
        print(f"  [extract] Text-heuristic derivation failed: {e}")

    # Path D: Groq LLM — explicit opt-in failsafe only, should essentially never trigger
    if os.getenv("LOFI_LLM_FAILSAFE") == "1":
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                dna = _derive_dna_from_groq(song, groq_key)
                print(f"  [extract] Groq failsafe used for '{song.title}'")
                return dna
            except Exception as e:
                print(f"  [extract] Groq failsafe failed: {e}")

    # Path E: absolute last-resort deterministic hash fallback (no text analysis)
    print(f"  [extract] Using hash-based fallback for '{song.title}'")
    return _derive_dna_from_hash(song)


# ─── Path A: MIDI scrape ───────────────────────────────────────────────────────

def _download_bitmidi(artist: str, title: str) -> bytes | None:
    """Search bitmidi.com for a MIDI file matching artist+title. Returns bytes or None."""
    global _last_bitmidi_req

    query = f"{artist} {title}"
    elapsed = time.time() - _last_bitmidi_req
    if elapsed < _BITMIDI_RATE_S:
        time.sleep(_BITMIDI_RATE_S - elapsed)
    _last_bitmidi_req = time.time()

    try:
        search_resp = requests.get(
            _BITMIDI_SEARCH,
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 lofi-inator (educational music research)"},
            timeout=10,
        )
        if search_resp.status_code != 200:
            return None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(search_resp.text, "html.parser")

        # Find first result link ending in .mid
        mid_link = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".mid") or "/midi/" in href:
                mid_link = href
                break

        if not mid_link:
            return None

        base = "https://bitmidi.com"
        if not mid_link.startswith("http"):
            mid_link = base + mid_link

        # Download the MIDI file
        time.sleep(0.5)
        midi_resp = requests.get(
            mid_link,
            headers={"User-Agent": "Mozilla/5.0 lofi-inator (educational music research)"},
            timeout=10,
        )
        if midi_resp.status_code == 200 and midi_resp.content[:4] == b"MThd":
            return midi_resp.content

    except Exception:
        pass

    return None


def _parse_midi_bytes(midi_bytes: bytes) -> dict:
    """
    Parse a MIDI file and extract musical characteristics.
    Returns: {bpm, key_signature, scale_guess, chord_root_pitchclass, note_density}
    """
    import mido

    mid = mido.MidiFile(file=io.BytesIO(midi_bytes))
    tempo_us = 500000  # default 120 BPM
    key_signature = "Am"
    all_notes: list[int] = []
    note_events = 0
    total_time_ticks = 0

    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                tempo_us = msg.tempo
            elif msg.type == "key_signature":
                key_signature = _parse_key_signature(msg.key)
            elif msg.type == "note_on" and msg.velocity > 0:
                all_notes.append(msg.note % 12)
                note_events += 1
            total_time_ticks += getattr(msg, "time", 0)

    bpm = 60_000_000 / tempo_us

    pitch_classes = sorted(set(all_notes))
    scale_guess = _detect_scale(pitch_classes)

    # Most frequent pitch class as "chord root"
    from collections import Counter
    pc_counts = Counter(all_notes)
    chord_root_pc = pc_counts.most_common(1)[0][0] if pc_counts else 0

    bars_estimate = max(1, total_time_ticks // (mid.ticks_per_beat * 4))
    note_density = note_events / bars_estimate

    # Markov chain: learn note-to-note transitions for melodically faithful covers
    markov_nodes: dict | None = None
    if len(all_notes) >= 4:
        try:
            from isobar import MarkovLearner
            learner = MarkovLearner()
            for n in all_notes:
                learner.register(n)
            markov_nodes = dict(learner.markov.nodes)
        except Exception:
            markov_nodes = None

    return {
        "bpm": bpm,
        "key_signature": key_signature,
        "scale_guess": scale_guess,
        "chord_root_pc": chord_root_pc,
        "note_density": note_density,
        "markov_nodes": markov_nodes,
    }


def _parse_key_signature(key_str: str) -> str:
    """Convert mido key signature string to one of _VALID_KEYS."""
    # mido returns e.g. "Am", "C", "Gmaj", "Bmin"
    key_str = key_str.replace("maj", "").replace("min", "m").strip()
    return _map_key_to_valid(key_str, mode=0 if "m" in key_str.lower() else 1)


def _detect_scale(pitch_classes: list[int]) -> str:
    """Match pitch classes against scale templates via Hamming distance."""
    if not pitch_classes:
        return "pent"

    best_scale = "pent"
    best_score = float("inf")
    pc_set = set(pitch_classes)

    for scale_name, template in _SCALE_TEMPLATES.items():
        template_set = set(template)
        # Symmetric difference normalized by union size
        diff = len(pc_set.symmetric_difference(template_set))
        if diff < best_score:
            best_score = diff
            best_scale = scale_name

    return best_scale


def _build_dna_from_midi_parse(song: "SongInfo", parsed: dict) -> "MidiDNA":
    from .models import MidiDNA

    original_bpm = parsed["bpm"]
    lofi_bpm = max(62, min(92, int(original_bpm * random.uniform(0.67, 0.73))))
    key = _map_key_to_valid(parsed["key_signature"], mode=1)
    scale = parsed["scale_guess"]

    mode = 0 if key in ("Am", "Dm", "Em", "Gm", "Cm") else 1
    density = "sparse" if parsed["note_density"] < 8 else "medium"
    subgenre = _pick_subgenre(valence=0.5, mode=mode, energy=0.5)

    return MidiDNA(
        source_title=song.title,
        source_artist=song.artist,
        original_bpm=original_bpm,
        dna_source="midi_parse",
        bpm=lofi_bpm,
        key=key,
        progression=random.choice(_MINOR_PROGS if mode == 0 else _MAJOR_PROGS),
        swing=round(random.uniform(0.62, 0.70), 2),
        mood=_pick_mood(valence=0.4, energy=0.4),
        melody_density=density,
        melody_scale=scale,
        bass_walking=True,
        drum_energy="medium",
        sub_genre=subgenre,
        drum_pattern_a=random.choice([0, 1, 2, 7]),
        drum_pattern_b=random.choice([3, 7]),
        markov_melody_nodes=parsed.get("markov_nodes"),
    )


# ─── Path B: Spotify features ──────────────────────────────────────────────────

def _derive_dna_from_spotify(song: "SongInfo", features: "SpotifyFeatures") -> "MidiDNA":
    from .models import MidiDNA

    # BPM: slow down 25-35% for lofi feel
    lofi_bpm = max(62, min(92, int(features.tempo * random.uniform(0.67, 0.73))))

    # Key: map Spotify pitch class + mode to nearest valid key
    key = _map_pitch_class_to_key(features.key, features.mode)

    # Scale from mode + valence + energy
    scale = _derive_scale(features.mode, features.valence, features.energy)

    # Progression from mode + valence + energy
    progression = _derive_progression(features.mode, features.valence, features.energy)

    # Sub-genre from quadrant
    subgenre = _pick_subgenre(features.valence, features.mode, features.energy)

    # Swing: higher swing for less danceable songs (more jazz feel)
    swing = round(0.62 + (1.0 - features.danceability) * 0.08, 2)

    # Drums: energy-based
    drum_a, drum_b = _derive_drums(features.energy)

    # Bass: walking for lower danceability (jazzier feel)
    bass_walking = features.danceability < 0.5

    # Mood phrase
    mood = _pick_mood(features.valence, features.energy)

    # Drum energy
    if features.energy > 0.7:
        drum_energy = "high"
    elif features.energy > 0.35:
        drum_energy = "medium"
    else:
        drum_energy = "low"

    # Density
    melody_density = "medium" if features.energy > 0.5 else "sparse"

    return MidiDNA(
        source_title=song.title,
        source_artist=song.artist,
        original_bpm=features.tempo,
        dna_source="spotify_features",
        bpm=lofi_bpm,
        key=key,
        progression=progression,
        swing=swing,
        mood=mood,
        melody_density=melody_density,
        melody_scale=scale,
        bass_walking=bass_walking,
        drum_energy=drum_energy,
        sub_genre=subgenre,
        drum_pattern_a=drum_a,
        drum_pattern_b=drum_b,
    )


def _map_pitch_class_to_key(pitch_class: int, mode: int) -> str:
    """Map Spotify pitch class (0-11) + mode to nearest _VALID_KEYS entry."""
    if mode == 0:  # minor
        candidates = ["Am", "Dm", "Em", "Gm", "Cm"]
    else:          # major
        candidates = ["C", "G", "F"]

    # Find candidate whose semitone offset is closest to Spotify's pitch_class
    best = candidates[0]
    best_dist = float("inf")
    for c in candidates:
        root_pc = _KEY_SEMITONES[c] % 12
        dist = min(abs(root_pc - pitch_class), 12 - abs(root_pc - pitch_class))
        if dist < best_dist:
            best_dist = dist
            best = c
    return best


def _map_key_to_valid(key_str: str, mode: int = 0) -> str:
    """
    Map an arbitrary key string (e.g. 'B', 'F#m', 'Bb') to nearest _VALID_KEYS.
    mode: 1=major, 0=minor (only used when key_str is ambiguous).
    """
    key_str = key_str.strip()

    # Direct match first
    if key_str in _VALID_KEYS:
        return key_str

    # Parse root note + minor indicator
    match = re.match(r"^([A-G][#b]?)(m)?", key_str)
    if not match:
        return "Am"

    root_str, minor_flag = match.group(1), match.group(2)
    is_minor = bool(minor_flag) or mode == 0

    note_to_pc = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
                  "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
                  "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
    pitch_class = note_to_pc.get(root_str, 0)
    return _map_pitch_class_to_key(pitch_class, 0 if is_minor else 1)


def _derive_scale(mode: int, valence: float, energy: float) -> str:
    if mode == 1:
        if valence > 0.6:
            return "major_pent"
        return "mixo"
    else:
        if energy > 0.5:
            return "dorian"
        if valence < 0.3:
            return "phryg"
        return "pent"


def _derive_progression(mode: int, valence: float, energy: float) -> int:
    if mode == 1:  # major
        if energy > 0.65:
            pool = [22, 16, 21, 28, 25]  # uplifting, driving
        elif valence > 0.5:
            pool = [17, 18, 20, 23, 29]  # floating major
        else:
            pool = [19, 24, 7]            # minimal major vamp
    else:  # minor
        if energy > 0.65:
            pool = [10, 3, 27, 6]        # neo-soul, high-energy
        elif valence < 0.35:
            pool = [14, 15, 2]           # dark/melancholic
        else:
            pool = [0, 1, 7, 13]         # classic lofi minor
    return random.choice(pool)


def _pick_subgenre(valence: float, mode: int, energy: float) -> str:
    # High energy major
    if mode == 1 and energy > 0.65:
        return random.choice(["lo_fi_funk", "city_pop", "hip_hop_lofi"])
    # Bright major
    if mode == 1 and valence > 0.5:
        return random.choice(["summer_vibes", "morning_lofi", "anime_lofi", "bedroom_pop"])
    # Neo-soul / R&B feel
    if mode == 0 and energy > 0.55 and valence > 0.4:
        return random.choice(["neo_soul", "lofi_rnb", "nujabes"])
    # Hip-hop energy
    if energy > 0.6:
        return random.choice(["hip_hop_lofi", "chillhop", "chill_beats"])
    # Dark/moody
    if mode == 0 and valence < 0.35:
        return random.choice(["dark_lofi", "piano_lofi", "lofi_classical"])
    # Chill/ambient
    if energy < 0.3:
        return random.choice(["ambient", "chill_beats", "piano_lofi"])
    # Default
    return random.choice(["chillhop", "study_lofi", "cozy_cafe", "lofi_jazz"])


def _derive_drums(energy: float) -> tuple[int, int]:
    if energy > 0.65:
        return random.choice([6, 8]), random.choice([2, 5])
    elif energy > 0.4:
        return random.choice([0, 1, 2]), random.choice([3, 7])
    else:
        return random.choice([7, 3]), random.choice([3, 0])


def _pick_mood(valence: float, energy: float) -> str:
    if valence > 0.5 and energy > 0.5:
        quadrant = "bright_high"
    elif valence > 0.5:
        quadrant = "bright_low"
    elif energy > 0.5:
        quadrant = "dark_high"
    else:
        quadrant = "dark_low"
    return random.choice(_MOOD_PHRASES[quadrant])


# ─── Path C: text-heuristic derivation (deterministic, no network, no LLM) ────

# Word → valence (sad/negative=low ... happy/positive=high) contribution
_VALENCE_KEYWORDS: dict[str, float] = {
    "love": 0.8, "loved": 0.8, "happy": 0.85, "sun": 0.75, "sunny": 0.75,
    "summer": 0.75, "smile": 0.8, "smiling": 0.8, "dance": 0.7, "dancing": 0.7,
    "sweet": 0.7, "gold": 0.65, "golden": 0.7, "bright": 0.75, "warm": 0.7,
    "good": 0.65, "joy": 0.85, "shine": 0.7, "shining": 0.7, "light": 0.6,
    "sky": 0.6, "free": 0.65, "young": 0.6, "beautiful": 0.7, "paradise": 0.75,
    "sad": 0.15, "sadness": 0.15, "cry": 0.15, "crying": 0.15, "alone": 0.2,
    "lonely": 0.15, "dark": 0.2, "pain": 0.1, "hurt": 0.15, "broken": 0.15,
    "goodbye": 0.25, "lost": 0.2, "rain": 0.3, "rainy": 0.3, "night": 0.35,
    "cold": 0.3, "blue": 0.3, "sorry": 0.25, "hate": 0.1, "fear": 0.15,
    "ghost": 0.25, "shadow": 0.25, "tears": 0.15, "grief": 0.1, "empty": 0.2,
    "cruel": 0.15, "sick": 0.2, "afraid": 0.2,
}

# Word → energy (calm/slow=low ... loud/intense=high) contribution
_ENERGY_KEYWORDS: dict[str, float] = {
    "dance": 0.85, "dancing": 0.85, "party": 0.9, "run": 0.8, "running": 0.8,
    "fire": 0.8, "fight": 0.85, "fighting": 0.85, "loud": 0.8, "wild": 0.75,
    "up": 0.6, "jump": 0.8, "hard": 0.7, "rock": 0.7, "beat": 0.65,
    "energy": 0.75, "power": 0.7, "alive": 0.65, "crazy": 0.7, "fast": 0.75,
    "slow": 0.15, "slowly": 0.15, "quiet": 0.15, "still": 0.15, "sleep": 0.1,
    "sleeping": 0.1, "calm": 0.15, "soft": 0.2, "softly": 0.2, "whisper": 0.15,
    "drift": 0.2, "drifting": 0.2, "float": 0.2, "floating": 0.2, "night": 0.3,
    "rain": 0.25, "chill": 0.2, "chilling": 0.2, "slow-motion": 0.1, "lazy": 0.15,
    "dream": 0.25, "dreaming": 0.25, "peace": 0.2, "peaceful": 0.15,
}

_WORD_RE = re.compile(r"[a-z']+")


def _infer_mood_from_text(text: str) -> tuple[float, float]:
    """Score (valence, energy) in [0,1] from keyword hits in title+artist text.
    Falls back to a neutral 0.5/0.5 midpoint when no known words are present —
    the deterministic hash-seeded RNG downstream still gives per-song variety."""
    words = _WORD_RE.findall(text.lower())
    v_hits = [_VALENCE_KEYWORDS[w] for w in words if w in _VALENCE_KEYWORDS]
    e_hits = [_ENERGY_KEYWORDS[w] for w in words if w in _ENERGY_KEYWORDS]
    valence = sum(v_hits) / len(v_hits) if v_hits else 0.5
    energy = sum(e_hits) / len(e_hits) if e_hits else 0.5
    return valence, energy


def _derive_dna_from_heuristic(song: "SongInfo") -> "MidiDNA":
    """
    Deterministic, text-aware derivation: infers mood/energy from the song's title+artist
    via a hand-built keyword lexicon (the same job Path D's LLM call used to do), then reuses
    the same valence/energy-driven derivation logic as the Spotify path (Path B) for
    scale/progression/sub-genre/drums. Same song -> same result every run; no network
    call, no LLM. This is the primary non-network fallback tier.
    """
    from .models import MidiDNA

    text = f"{song.title} {song.artist}"
    valence, energy = _infer_mood_from_text(text)

    seed_str = f"{song.artist_slug}:{song.title_slug}"
    digest = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)

    # Seed the shared `random` module deterministically for this song only, then restore
    # non-deterministic global state afterward so we don't affect unrelated callers.
    state = random.getstate()
    random.seed(digest)
    try:
        mode = 1 if valence >= 0.5 else 0
        key = _map_pitch_class_to_key(digest % 12, mode)
        scale = _derive_scale(mode, valence, energy)
        progression = _derive_progression(mode, valence, energy)
        subgenre = _pick_subgenre(valence, mode, energy)
        drum_a, drum_b = _derive_drums(energy)
        swing = round(0.62 + ((digest // 12) % 100) / 100 * 0.08, 2)
        bass_walking = energy < 0.45
        mood = _pick_mood(valence, energy)
        drum_energy = "high" if energy > 0.7 else "medium" if energy > 0.35 else "low"
        melody_density = "medium" if energy > 0.5 else "sparse"
        lofi_bpm = max(62, min(92, int(72 + (energy - 0.5) * 30)))
    finally:
        random.setstate(state)

    return MidiDNA(
        source_title=song.title,
        source_artist=song.artist,
        original_bpm=lofi_bpm / 0.70,
        dna_source="text_heuristic",
        bpm=lofi_bpm,
        key=key,
        progression=progression,
        swing=swing,
        mood=mood,
        melody_density=melody_density,
        melody_scale=scale,
        bass_walking=bass_walking,
        drum_energy=drum_energy,
        sub_genre=subgenre,
        drum_pattern_a=drum_a,
        drum_pattern_b=drum_b,
    )


# ─── Path D: Groq LLM derivation (opt-in failsafe only) ───────────────────────

_GROQ_PROMPT = """Given the mainstream song "{title}" by "{artist}", derive parameters to create
a lo-fi hip hop inspired cover track. Output ONLY valid JSON (no markdown) matching this schema:
{{
  "bpm": <int 62-92>,
  "key": <one of "Am","Dm","Em","Gm","Cm","C","G","F">,
  "progression": <int 0-30>,
  "swing": <float 0.60-0.70>,
  "mood": "<short atmospheric phrase matching the song vibe, lofi style>",
  "melody_density": <"sparse" or "medium">,
  "melody_scale": <one of "pent","dorian","major_pent","major","lydian","mixo","phryg">,
  "bass_walking": <true or false>,
  "drum_energy": <"low","medium","high">,
  "sub_genre": <one of "chillhop","lofi_jazz","dark_lofi","bossa_lofi","neo_soul","ambient","nujabes","city_pop","morning_lofi","hip_hop_lofi","chill_beats","cozy_cafe","anime_lofi","summer_vibes","study_lofi","jazz_cafe","piano_lofi","bedroom_pop","lofi_rnb","lofi_classical">,
  "drum_pattern_a": <int 0-10>,
  "drum_pattern_b": <int 0-10>
}}

Make the track musically related to the original song's vibe and key, slowed to lofi tempo."""


def _derive_dna_from_groq(song: "SongInfo", groq_key: str) -> "MidiDNA":
    import json as _json
    from .models import MidiDNA
    from groq import Groq

    client = Groq(api_key=groq_key)
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": _GROQ_PROMPT.format(
            title=song.title, artist=song.artist
        )}],
        temperature=0.9,
    )
    raw = resp.choices[0].message.content.strip()
    if "```" in raw:
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```"))
    s, e = raw.find("{"), raw.rfind("}") + 1
    p = _json.loads(raw[s:e])

    n_pats = 11  # len(DRUM_PATTERNS) — avoid importing the large module
    return MidiDNA(
        source_title=song.title,
        source_artist=song.artist,
        original_bpm=float(p.get("bpm", 80)) / 0.70,  # estimate original BPM
        dna_source="groq_derive",
        bpm=max(62, min(92, int(p.get("bpm", 78)))),
        key=p.get("key", "Am") if p.get("key", "Am") in _VALID_KEYS else "Am",
        progression=int(p.get("progression", 0)) % 31,
        swing=max(0.58, min(0.70, float(p.get("swing", 0.62)))),
        mood=str(p.get("mood", "lofi dreams")),
        melody_density=p.get("melody_density", "sparse"),
        melody_scale=p.get("melody_scale", "pent"),
        bass_walking=bool(p.get("bass_walking", False)),
        drum_energy=p.get("drum_energy", "medium"),
        sub_genre=p.get("sub_genre", "chillhop") if p.get("sub_genre", "") in _VALID_SUBGENRES else "chillhop",
        drum_pattern_a=int(p.get("drum_pattern_a", 0)) % n_pats,
        drum_pattern_b=int(p.get("drum_pattern_b", 3)) % n_pats,
    )


# ─── Path E: absolute last-resort hash-based fallback ─────────────────────────

def _derive_dna_from_hash(song: "SongInfo") -> "MidiDNA":
    """Deterministic fallback: same song → same params, every time."""
    from .models import MidiDNA

    seed_str = f"{song.artist_slug}:{song.title_slug}"
    digest = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    rng = random.Random(digest)

    key = rng.choice(_VALID_KEYS)
    mode = 0 if key in ("Am", "Dm", "Em", "Gm", "Cm") else 1
    progression = rng.choice(_MINOR_PROGS if mode == 0 else _MAJOR_PROGS)
    subgenre = rng.choice(_VALID_SUBGENRES[:12])  # stick to common ones for fallback

    return MidiDNA(
        source_title=song.title,
        source_artist=song.artist,
        original_bpm=100.0,
        dna_source="fallback",
        bpm=rng.randint(68, 88),
        key=key,
        progression=progression,
        swing=round(rng.uniform(0.62, 0.70), 2),
        mood="the night rain has its own soundtrack",
        melody_density="sparse",
        melody_scale=rng.choice(["pent", "dorian", "major_pent"]),
        bass_walking=rng.random() < 0.4,
        drum_energy="medium",
        sub_genre=subgenre,
        drum_pattern_a=rng.choice([0, 1, 2, 7]),
        drum_pattern_b=rng.choice([3, 7]),
    )
