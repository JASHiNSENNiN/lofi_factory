"""
titles.py — video titles that read like a place you'd want to sit in.

The lofi convention (Lofi Girl, Chillhop and their imitators) is a short
scene or mood, an emoji, then the genre and use in brackets:
"lofi hip hop radio 📚 beats to relax/study to", "Nighttime Ramen [jazzy
beats / lofi hip hop mix]". Title research points the same way: 40-60
characters, the searched keyword in the first few words.

Every scene phrase here was written by hand to be grammatical and to match
what the video shows: phrases are tied to the visual theme (the thumbnail's
window and the video loop show that same theme), filtered by season, and
kept to four words or fewer so the same phrase can be the thumbnail text.
Trends only reorder these phrases (see trend_weights); they never put a
word into a title that doesn't describe the video.
"""
from __future__ import annotations

import datetime
import random
import re
from collections import Counter

# Visual theme -> scenes. All lowercase (the genre's house style), <= 4 words.
SCENES: dict[str, list[str]] = {
    "cozy_rain":      ["rain on the window", "rainy night study", "listening to the rain",
                       "rain and warm coffee", "a rainy evening in"],
    "midnight_cafe":  ["midnight coffee", "the last café open", "coffee after midnight",
                       "a quiet corner café"],
    "purple_dusk":    ["dusk on the rooftop", "when the city glows", "purple evening sky",
                       "twilight thoughts"],
    "amber_night":    ["candlelight and pages", "a slow amber night", "warm light, late hours"],
    "winter_snow":    ["first snow of winter", "snowy night in", "quiet snowfall",
                       "warm room, cold night"],
    "autumn_study":   ["autumn study session", "falling leaves outside", "golden autumn light",
                       "sweater weather"],
    "spring_dawn":    ["spring morning light", "windows open in spring", "soft spring dawn"],
    "neon_tokyo":     ["neon city at 2am", "city lights below", "late train home",
                       "rain on neon streets"],
    "summer_lofi":    ["summer sunset", "golden hour drive", "warm summer evening",
                       "sun-faded afternoon"],
    "blue_hour":      ["the blue hour", "after the sun sets", "quiet blue evening"],
    "forest_rain":    ["rain in the forest", "cabin in the rain", "green leaves, grey skies"],
    "sakura_night":   ["cherry blossom night", "petals in the moonlight", "a spring night walk"],
    "vaporwave":      ["mall at closing time", "sunset in 1987", "dreams in pastel"],
    "lofi_house":     ["dancing alone at 2am", "late night grooves", "warm basement lights"],
    "lofi_classical": ["moonlight and piano", "candlelit piano", "a quiet recital"],
    "bedroom_pop":    ["bedroom daydreams", "fairy lights and posters", "headphones on, world off"],
    "lofi_rnb":       ["slow night drive", "late night feelings", "velvet midnight"],
}
# Used when the season filter empties a theme's list; split by time of day
# so a dawn theme never falls back to "late night".
_FALLBACK_NIGHT = ["late night study", "a cozy evening in", "quiet hours"]
_FALLBACK_DAY = ["slow mornings", "a quiet afternoon", "soft daylight"]

EMOJI: dict[str, str] = {
    "cozy_rain": "🌧️", "midnight_cafe": "☕", "purple_dusk": "🌆", "amber_night": "🕯️",
    "winter_snow": "❄️", "autumn_study": "🍂", "spring_dawn": "🌸", "neon_tokyo": "🌃",
    "summer_lofi": "🌅", "blue_hour": "🌙", "forest_rain": "🌿", "sakura_night": "🌸",
    "vaporwave": "🌴", "lofi_house": "💿", "lofi_classical": "🎹", "bedroom_pop": "🛏️",
    "lofi_rnb": "🌙",
}

# One adjective per theme for the "radio" form: "rainy beats to study & relax to".
_ADJ: dict[str, str] = {
    "cozy_rain": "rainy", "midnight_cafe": "late night", "purple_dusk": "dreamy",
    "amber_night": "warm", "winter_snow": "snowy", "autumn_study": "autumn",
    "spring_dawn": "soft", "neon_tokyo": "neon", "summer_lofi": "sunny",
    "blue_hour": "calm", "forest_rain": "rainy", "sakura_night": "dreamy",
    "vaporwave": "hazy", "lofi_house": "groovy", "lofi_classical": "gentle",
    "bedroom_pop": "dreamy", "lofi_rnb": "smooth",
}

_SEASONS = {"winter": (12, 1, 2), "snow": (11, 12, 1, 2, 3), "spring": (3, 4, 5),
            "blossom": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11),
            "leaves": (9, 10, 11), "sweater": (10, 11, 12, 1, 2)}

_NIGHT_THEMES = {"cozy_rain", "midnight_cafe", "amber_night", "winter_snow", "neon_tokyo",
                 "blue_hour", "sakura_night", "lofi_house", "lofi_classical", "lofi_rnb",
                 "purple_dusk", "bedroom_pop"}
_NIGHT_TIMES = ["after midnight", "at 2am", "late at night"]
_DAY_TIMES = ["on a slow morning", "at golden hour", "on a sunday afternoon"]

STRATEGIES = ("scene", "moment", "radio")

# Activities that read well before a time ("coding after midnight"); the
# rest of the concept pool ("first week of classes") falls back to studying.
_MOMENT_ACTIVITIES = {
    "coding", "essay writing", "studying", "reading", "journaling", "math homework",
    "piano practice", "novel writing", "research", "design work", "exam prep", "gaming",
    "drawing", "cooking", "cleaning", "learning guitar", "meditation", "interview prep",
    "language learning", "working from home",
}

_WORD = re.compile(r"[a-z]+")
_STOP = {"lofi", "lo", "fi", "hip", "hop", "beats", "to", "the", "a", "and", "music",
         "mix", "for", "study", "relax", "of", "in", "on", "hour", "hours", "radio"}


def in_season(phrase: str, month: int | None = None) -> bool:
    month = month or datetime.datetime.now(datetime.timezone.utc).month
    return all(month in months for word, months in _SEASONS.items() if word in phrase)


def trend_weights(trends: dict | None) -> Counter:
    """Descriptive words in what's trending this week (competitor titles and
    the snapshot's seasonal keywords), minus genre boilerplate."""
    words: Counter = Counter()
    if not trends:
        return words
    for t in list(trends.get("trending_titles") or []) + list(trends.get("seasonal_keywords") or []):
        for w in _WORD.findall(str(t).lower()):
            if w not in _STOP and len(w) > 2:
                words[w] += 1
    return words


def pick_scene(theme: str, trends: dict | None = None, month: int | None = None,
               rng: random.Random | None = None) -> str:
    """A scene for this theme and season; phrases sharing words with what's
    trending are proportionally more likely."""
    rng = rng or random
    pool = [s for s in SCENES.get(theme, []) if in_season(s, month)]
    pool = pool or (_FALLBACK_NIGHT if theme in _NIGHT_THEMES else _FALLBACK_DAY)
    tw = trend_weights(trends)
    weights = [1.0 + 2.0 * sum(tw[w] for w in _WORD.findall(s)) for s in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def _genre_tag(genre: str) -> str:
    g = (genre or "lofi hip hop").strip().lower()
    return "lofi hip hop" if g == "lo-fi hip hop" else g


def build(strategy: str, *, theme: str, genre: str, activity: str, duration: str,
          trends: dict | None = None, month: int | None = None,
          rng: random.Random | None = None) -> tuple[str, str]:
    """(title, thumbnail_text) for one strategy. Titles stay within ~60
    characters: the length tag is dropped first if it would run over."""
    rng = rng or random
    emoji = EMOJI.get(theme, "✨")
    g = _genre_tag(genre)
    scene = pick_scene(theme, trends, month, rng)
    if strategy == "moment":
        when = rng.choice(_NIGHT_TIMES if theme in _NIGHT_THEMES else _DAY_TIMES)
        act = activity if activity in _MOMENT_ACTIVITIES else "studying"
        head = f"{act} {when}"
        # Thumbnail text stays at four words or fewer (readable on a phone).
        thumb = head if len(head.split()) <= 4 else scene
    elif strategy == "radio":
        adj = _ADJ.get(theme, "chill")
        head, thumb = f"{g} {emoji} {adj} beats to study & relax to", scene
        title = f"{head} · {duration}"
        return (title if len(title) <= 62 else head), thumb
    else:
        head = thumb = scene
    title = f"{head} {emoji} [{g} · {duration}]"
    if len(title) > 62:
        title = f"{head} {emoji} [{g}]"
    return title, thumb
