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
                       "rain and warm coffee", "a rainy evening in", "storm out, tea in",
                       "puddles and streetlights", "rain until morning"],
    "midnight_cafe":  ["midnight coffee", "the last café open", "coffee after midnight",
                       "a quiet corner café", "one more espresso", "the 2am barista",
                       "steam on the glass"],
    "purple_dusk":    ["dusk on the rooftop", "when the city glows", "purple evening sky",
                       "twilight thoughts", "streetlights coming on", "the sky turns violet"],
    "amber_night":    ["candlelight and pages", "a slow amber night", "warm light, late hours",
                       "old records, low light", "honey-coloured evening", "lamplight and letters"],
    "winter_snow":    ["first snow of winter", "snowy night in", "quiet snowfall",
                       "warm room, cold night", "frost on the window", "snow on the rooftops",
                       "blankets and cocoa"],
    "autumn_study":   ["autumn study session", "falling leaves outside", "golden autumn light",
                       "sweater weather", "maple leaves and tea", "october afternoon",
                       "leaves on the sill"],
    "spring_dawn":    ["spring morning light", "windows open in spring", "soft spring dawn",
                       "birdsong at sunrise", "first light, fresh air", "a gentle spring morning"],
    "neon_tokyo":     ["neon city at 2am", "city lights below", "late train home",
                       "rain on neon streets", "vending machine glow", "last train, empty car",
                       "convenience store light"],
    "summer_lofi":    ["summer sunset", "golden hour drive", "warm summer evening",
                       "sun-faded afternoon", "windows down, sun low", "the beach at dusk",
                       "long summer days"],
    "blue_hour":      ["the blue hour", "after the sun sets", "quiet blue evening",
                       "the world slows down", "lights on, sky blue", "blue skies fading"],
    "forest_rain":    ["rain in the forest", "cabin in the rain", "green leaves, grey skies",
                       "moss and mist", "rain on the pines", "cabin in the woods"],
    "sakura_night":   ["cherry blossom night", "petals in the moonlight", "a spring night walk",
                       "petals on the river", "lanterns and blossoms", "under the sakura"],
    "vaporwave":      ["mall at closing time", "sunset in 1987", "dreams in pastel",
                       "an empty food court", "neon palm trees", "a vhs summer"],
    "lofi_house":     ["dancing alone at 2am", "late night grooves", "warm basement lights",
                       "the after-party glow", "kitchen dance floor", "records till sunrise"],
    "lofi_classical": ["moonlight and piano", "candlelit piano", "a quiet recital",
                       "nocturne by the window", "piano next door", "old sheet music"],
    "bedroom_pop":    ["bedroom daydreams", "fairy lights and posters", "headphones on, world off",
                       "polaroids on the wall", "a soft sunday", "talking to the ceiling"],
    "lofi_rnb":       ["slow night drive", "late night feelings", "velvet midnight",
                       "city lights, slow heart", "texts we never sent", "a warm late call"],
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
    "vaporwave": "hazy", "lofi_house": "late night", "lofi_classical": "gentle",
    "bedroom_pop": "dreamy", "lofi_rnb": "smooth",
}

_SEASONS = {"winter": (12, 1, 2), "snow": (11, 12, 1, 2, 3), "spring": (3, 4, 5),
            "blossom": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11),
            "leaves": (9, 10, 11), "sweater": (10, 11, 12, 1, 2), "october": (10,),
            "maple": (9, 10, 11), "frost": (11, 12, 1, 2, 3), "cocoa": (11, 12, 1, 2),
            "petals": (3, 4, 5), "sakura": (3, 4, 5)}

_NIGHT_THEMES = {"cozy_rain", "midnight_cafe", "amber_night", "winter_snow", "neon_tokyo",
                 "blue_hour", "sakura_night", "lofi_house", "lofi_classical", "lofi_rnb",
                 "purple_dusk", "bedroom_pop"}
_NIGHT_TIMES = ["after midnight", "at 2am", "late at night", "at 3am", "past midnight",
                "on a quiet night"]
_DAY_TIMES = ["on a slow morning", "at golden hour", "on a sunday afternoon",
              "with morning coffee", "on a quiet afternoon", "before sunset"]

STRATEGIES = ("scene", "moment", "radio")
THUMB_MAX_CHARS = 24    # the longest scene phrase; longer text shrinks on the card

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


def _use_phrase(genre: str) -> str:
    """What the music is for, in the genre's own idiom: sleep music isn't
    for studying, and ambient has no beats."""
    if "sleep" in genre:
        return "music to fall asleep to"
    if "ambient" in genre:
        return "music to drift away to"
    if any(w in genre for w in ("house", "garage", "funk", "city pop", "synthwave")):
        return "grooves to work & unwind to"
    return "beats to study & relax to"


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
        # Thumbnail text stays short enough to read on a phone.
        thumb = head if len(head.split()) <= 4 and len(head) <= THUMB_MAX_CHARS else scene
    elif strategy == "radio":
        adj = _ADJ.get(theme, "chill")
        head, thumb = f"{g} {emoji} {adj} {_use_phrase(g)}", scene
        title = f"{head} · {duration}"
        return (title if len(title) <= 62 else head), thumb
    else:
        head = thumb = scene
    title = f"{head} {emoji} [{g} · {duration}]"
    if len(title) > 62:
        title = f"{head} {emoji} [{g}]"
    return title, thumb


# Sub-genre -> themes that look like it sounds. Genres with no clear look
# (plain lofi hip hop, chillhop, study beats) get any in-season theme.
_GENRE_THEMES: dict[str, tuple[str, ...]] = {
    "lofi_jazz": ("midnight_cafe", "amber_night", "cozy_rain"),
    "jazz_cafe": ("midnight_cafe", "amber_night", "cozy_rain"),
    "cozy_cafe": ("midnight_cafe", "amber_night", "cozy_rain"),
    "nujabes": ("amber_night", "midnight_cafe", "cozy_rain"),
    "neo_soul": ("lofi_rnb", "amber_night", "purple_dusk"),
    "lofi_rnb": ("lofi_rnb", "amber_night", "purple_dusk"),
    "bossa_lofi": ("summer_lofi", "blue_hour", "spring_dawn"),
    "summer_vibes": ("summer_lofi", "spring_dawn"),
    "ambient": ("blue_hour", "winter_snow", "forest_rain"),
    "sleep_lofi": ("blue_hour", "winter_snow", "forest_rain"),
    "city_pop": ("neon_tokyo", "purple_dusk"),
    "dark_lofi": ("neon_tokyo", "midnight_cafe", "cozy_rain"),
    "lofi_phonk": ("neon_tokyo", "midnight_cafe"),
    "lofi_drill": ("neon_tokyo", "cozy_rain"),
    "lofi_house": ("lofi_house", "neon_tokyo"),
    "lofi_garage": ("lofi_house", "neon_tokyo"),
    "lofi_synthwave": ("vaporwave", "purple_dusk"),
    "vaporwave": ("vaporwave", "purple_dusk"),
    "lofi_classical": ("lofi_classical", "winter_snow", "amber_night"),
    "piano_lofi": ("lofi_classical", "winter_snow", "amber_night"),
    "bedroom_pop": ("bedroom_pop", "purple_dusk"),
    "anime_lofi": ("sakura_night", "blue_hour", "purple_dusk"),
    "morning_lofi": ("spring_dawn", "summer_lofi", "autumn_study"),
}
# Themes whose picture belongs to one time of year.
_THEME_MONTHS = {"winter_snow": (11, 12, 1, 2, 3), "sakura_night": (3, 4, 5),
                 "autumn_study": (9, 10, 11), "spring_dawn": (3, 4, 5, 6)}


def theme_in_season(theme: str, month: int | None = None) -> bool:
    month = month or datetime.datetime.now(datetime.timezone.utc).month
    return month in _THEME_MONTHS.get(theme, range(1, 13))


def theme_for_genre(sub_genre: str | None, month: int | None = None,
                    rng: random.Random | None = None) -> str:
    """A visual theme that fits the genre that plays and the time of year
    (no snow in July, no sunny beach for sleep music)."""
    rng = rng or random
    fitting = [t for t in _GENRE_THEMES.get(sub_genre or "", ()) if theme_in_season(t, month)]
    return rng.choice(fitting or [t for t in SCENES if theme_in_season(t, month)])
