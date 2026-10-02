"""
generate_seo.py  v2 — Concept-Driven Edition
=============================================
Every video gets a UNIQUE CONCEPT: a specific setting, story, and emotional
hook that gives each upload genuine search value and prevents duplicate-content
detection across thousands of uploads.

CONCEPT PILLARS (5 × many combinations = effectively infinite unique videos):
  1. Temporal    — time anchor            (4am deadline, midnight focus, golden hour)
  2. Activity    — specific task          (coding session, essay, art class, language study)
  3. Emotional   — state of mind          (productively sad, overstimulated → calm)
  4. Aesthetic   — visual/cultural genre  (dark academia, cottagecore, anime bedroom)
  5. Cross-genre — music fusion           (lofi jazz, bossa nova study, lofi classical)

Each concept generates a unique:
  · Title (story-hook format, under 70 chars)
  · Description (short scene-setter + CTA; tracklist added after assembly)
  · Tags (broad + mid + long-tail + concept-specific)
  · Chapter labels matching the concept narrative

Concepts come from a combinatorial pool of hand-written phrases (300+
base combinations); nothing here calls an external text generator.

Output: assets/seo_TIMESTAMP.json
"""

import os, json, random, datetime, secrets, re


try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets')
os.makedirs(ASSETS_DIR, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
#  CONCEPT POOLS
#  Combinatorial design: temporal × activity × emotional gives thousands of
#  unique base combos. Each renders a different title + description + tags.
# ──────────────────────────────────────────────────────────────────────────────

TIME_POOL = [
    # (time_label, mood_line, tags_extra)
    ("3am",           "the whole world is asleep except you",
     ["3am lofi", "late night study music", "cant sleep lofi", "3am vibes"]),
    ("2am",           "still awake, still going",
     ["2am lofi", "late night lofi", "2am study", "nightowl lofi"]),
    ("midnight",      "the hour when focus sharpens",
     ["midnight lofi", "midnight study music", "midnight vibes lofi"]),
    ("4am",           "you forgot sleep exists",
     ["4am lofi", "4am study session", "all nighter music", "4am beats"]),
    ("golden hour",   "that ten minutes before everything changes",
     ["golden hour lofi", "sunset lofi", "evening lofi", "afternoon lofi"]),
    ("late evening",  "the day is almost done",
     ["evening lofi", "night study music", "late evening lofi"]),
    ("sunday morning","nowhere to be, nothing to rush",
     ["sunday lofi", "morning lofi", "weekend lofi", "lazy morning lofi"]),
    ("rainy tuesday", "productivity and petrichor",
     ["rainy day lofi", "rain lofi", "rainy study music", "study with rain sounds"]),
    ("winter night",  "cold outside, warm in here",
     ["winter lofi", "winter study music", "snow lofi", "cozy winter beats"]),
    ("autumn dusk",   "leaves and lengthening shadows",
     ["autumn lofi", "fall lofi", "october lofi", "autumn vibes"]),
    ("spring rain",   "windows open, fresh air",
     ["spring lofi", "spring study music", "april lofi", "rain lofi"]),
    ("summer night",  "warm air, distant music",
     ["summer night lofi", "summer lofi", "warm night lofi"]),
    ("5am",           "watched the sunrise happen by accident",
     ["5am lofi", "sunrise lofi", "early morning lofi", "dawn lofi"]),
    ("dead of night", "silence except for the hum",
     ["night lofi", "dark lofi", "silent night lofi", "deep night lofi"]),
    ("pre-dawn",      "the sky turns that impossible blue",
     ["pre dawn lofi", "early lofi", "quiet morning lofi"]),
    ("friday night",  "chose productivity over going out",
     ["friday night lofi", "staying in lofi", "productive night lofi"]),
    ("monday",        "slow start, steady finish",
     ["monday lofi", "work from home lofi", "monday motivation music"]),
    ("study session", "hours disappearing one track at a time",
     ["study session lofi", "long study music", "focus session lofi"]),
    ("between meetings",   "the eleven minutes you'd rather not waste",
     ["work break lofi", "between meetings music", "short focus lofi", "micro session lofi"]),
    ("the commute home",   "decompressing at thirty miles an hour",
     ["commute lofi", "end of day lofi", "unwinding lofi", "evening commute music"]),
    ("first of the month", "everything resets, nothing changes, somehow okay",
     ["new month lofi", "fresh start music", "reset lofi", "monthly lofi"]),
    ("6am alarm",          "the negotiation between ambition and the pillow",
     ["early morning lofi", "6am lofi", "alarm lofi", "wakeup music"]),
    ("last day of the year","every memory playing back at once",
     ["new year lofi", "december lofi", "year end lofi", "reflection lofi"]),
    ("half-past nowhere",  "no clocks. no plans. just this.",
     ["timeless lofi", "no plans lofi", "free time lofi", "unscheduled lofi"]),
    ("the afternoon slump","2pm gravity and coffee wearing off",
     ["afternoon slump lofi", "2pm lofi", "afternoon focus", "midday lofi"]),
    ("thursday night",     "almost the weekend, almost anything",
     ["thursday lofi", "almost friday lofi", "mid week lofi", "thursday vibes"]),
    ("the quiet hour",     "between kids to bed and actually sleeping",
     ["quiet hour lofi", "peaceful night lofi", "me time lofi", "evening alone lofi"]),
    ("deadline eve",       "you've done harder things. probably.",
     ["deadline lofi", "crunch time music", "last minute study lofi", "deadline music"]),
    ("after the storm",    "clean air and the silence that follows a hard week",
     ["recovery lofi", "post storm lofi", "calm after lofi", "breathing space music"]),
]

ACTIVITY_POOL = [
    # (activity, context, tags_extra)
    ("coding",          "side project that actually matters",
     ["coding lofi", "programming music", "developer playlist", "lofi to code to"]),
    ("essay writing",   "deadline in six hours, you're fine",
     ["essay writing music", "writing lofi", "lofi for writing", "essay deadline lofi"]),
    ("art",             "sketchbook open, reference tab open next to it",
     ["art lofi", "drawing music", "creative lofi", "artist playlist"]),
    ("studying",        "notes open, phone face-down",
     ["study music", "lofi study beats", "focus study music", "exam prep lofi"]),
    ("reading",         "the book you've been putting off since January",
     ["reading music", "book lofi", "library lofi", "reading playlist"]),
    ("working from home","second monitor, third coffee",
     ["work from home music", "wfh lofi", "remote work lofi", "productivity music"]),
    ("language learning","vocab cards and podcast on pause",
     ["language learning music", "study japanese lofi", "language study", "duolingo lofi"]),
    ("journaling",      "the thoughts that only make sense at 1am",
     ["journaling music", "journal lofi", "writing thoughts lofi", "reflective lofi"]),
    ("game dev",        "prototype running in one window, docs in another",
     ["game dev lofi", "gamedev music", "indie dev lofi", "coding game music"]),
    ("math homework",   "the kind of focus that makes everything else disappear",
     ["math lofi", "homework music", "algebra lofi", "stem study music"]),
    ("piano practice",  "the same eight bars, slower and slower until they're right",
     ["piano lofi", "music practice lofi", "musician lofi"]),
    ("novel writing",   "chapter twelve, still not sure where this is going",
     ["novel writing music", "author lofi", "creative writing lofi"]),
    ("research",        "fifteen tabs and a cold coffee",
     ["research music", "academic lofi", "thesis music", "research lofi"]),
    ("design work",     "figma open, spotify paused, this on instead",
     ["design lofi", "designer music", "creative work lofi", "ui ux music"]),
    ("night shift",     "everyone else clocked out hours ago",
     ["night shift music", "overnight lofi", "work night shift", "late work lofi"]),
    ("exam prep",       "the day before. you got this.",
     ["exam music", "exam prep lofi", "study exam lofi", "test prep music"]),
    ("gaming",          "controller in hand, between checkpoints",
     ["gaming lofi", "chill gaming music", "rpg lofi", "lo fi gaming beats"]),
    ("drawing",         "reference photo up, hand moving on autopilot",
     ["drawing music", "art lofi", "creative lofi", "sketch music lofi"]),
    ("cooking",         "mise en place on the counter, something simmering",
     ["cooking music", "kitchen lofi", "cooking playlist lofi", "chill cooking beats"]),
    ("commuting",       "city sliding past the window",
     ["commute music", "commuting lofi", "train lofi", "travel music lofi"]),
    ("cleaning",        "putting the apartment back in order, brain on standby",
     ["cleaning music", "cleaning playlist lofi", "tidying lofi", "housework music"]),
    ("grad school",         "three papers, two deadlines, one cup left",
     ["grad school lofi", "phd lofi", "dissertation music", "postgrad study music"]),
    ("learning guitar",     "the same chord transition, slower each time",
     ["guitar practice lofi", "musician lofi", "instrument practice music"]),
    ("therapy homework",    "writing the things you almost said out loud",
     ["therapy lofi", "mental health music", "reflective lofi", "healing study music"]),
    ("portfolio building",  "making something to show for all these hours",
     ["portfolio music", "creative work lofi", "designer lofi", "artist work music"]),
    ("learning to cook",    "recipe open, timer set, knife uncertain",
     ["cooking school lofi", "beginner cook music", "kitchen learning lofi"]),
    ("meditation",          "five minutes that take twenty to begin",
     ["meditation music", "mindfulness lofi", "calm music", "breathe lofi"]),
    ("side project",        "the thing you actually care about, after hours",
     ["side project lofi", "passion project music", "maker lofi", "builder music"]),
    ("interview prep",      "the answer is good. the answer is good. the answer",
     ["interview prep music", "job interview lofi", "preparation lofi", "focus career music"]),
    ("learning a language", "third time through the same phrase. getting closer.",
     ["language learning lofi", "study language music", "polyglot lofi", "vocab lofi"]),
    ("wedding planning",    "spreadsheets for love. a reasonable thing to do.",
     ["wedding planning music", "event planning lofi", "organizational lofi"]),
    ("tax season",          "receipts everywhere, focus everywhere else",
     ["tax season lofi", "financial planning music", "accounting lofi", "adult responsibilities lofi"]),
    ("first week of classes","names to learn, a campus to map, a self to update",
     ["new semester lofi", "college lofi", "first week music", "campus study lofi"]),
    ("remote work Friday",  "nobody will know if you play this all afternoon",
     ["wfh friday lofi", "remote friday music", "home office lofi", "end of week lofi"]),
]

EMOTIONAL_POOL = [
    # (emotional_state, description, tags_extra)
    ("productively sad",
     "the kind of sad that makes you want to clean your whole apartment at midnight",
     ["sad lofi", "emotional lofi", "melancholy lofi", "sad beats to study to"]),
    ("overstimulated → calm",
     "too much input all day. this is the antidote.",
     ["calm lofi", "anxiety relief music", "calming lofi", "stress relief music"]),
    ("focused but exhausted",
     "running on fumes but the deadline doesn't care",
     ["tired but focused lofi", "exhausted study music", "push through lofi"]),
    ("nostalgic",
     "for a time you can't name, a place you've never been",
     ["nostalgic lofi", "nostalgia beats", "memory lofi", "vintage lofi"]),
    ("quietly hopeful",
     "things are uncertain. but here, right now, it's okay.",
     ["hopeful lofi", "positive lofi", "uplifting lofi", "feel good lofi"]),
    ("deep in the zone",
     "flow state. do not disturb.",
     ["flow state music", "deep focus lofi", "concentration music", "zone lofi"]),
    ("behind but calm",
     "you should be stressed. you're choosing not to be.",
     ["calm under pressure lofi", "deadline lofi", "productive calm"]),
    ("lonely but okay",
     "company is overrated anyway.",
     ["alone lofi", "introverted lofi", "solo session lofi", "introvert music"]),
    ("second wind",
     "2am and suddenly you can think again",
     ["second wind lofi", "late night energy lofi", "night owl study"]),
    ("introspective",
     "questions without answers. that's fine.",
     ["introspective lofi", "thinking music", "meditation lofi", "mindful lofi"]),
    ("healing",
     "one small step at a time.",
     ["healing lofi", "therapeutic music", "lofi for anxiety", "mental health lofi"]),
    ("determined",
     "soft music for hard work.",
     ["determined lofi", "motivation lofi", "grind lofi", "hustle beats"]),
    ("quietly devastated",
     "functional. mostly functional. fine.",
     ["sad lofi", "emotional lofi", "quiet devastation lofi", "coping lofi"]),
    ("the good kind of tired",
     "earned rest. the kind you don't feel guilty about.",
     ["rest lofi", "earned tired lofi", "end of long day lofi", "recovery lofi"]),
    ("optimistically overwhelmed",
     "too many ideas, not enough hours. somehow beautiful.",
     ["overwhelmed lofi", "busy brain music", "creative chaos lofi", "ambitious lofi"]),
    ("softly grieving",
     "it comes in waves. this is a wave. let it.",
     ["grief lofi", "loss lofi", "gentle sadness music", "mourning lofi"]),
    ("running on fumes",
     "past tired, past sense, somehow still moving forward",
     ["exhausted lofi", "running on empty music", "pulling through lofi", "late night grind"]),
    ("unbothered",
     "not checked out. just very, very calm.",
     ["unbothered lofi", "calm lofi", "peace music", "serenity lofi"]),
    ("creatively blocked",
     "the blank page has won every argument so far",
     ["creative block lofi", "writers block music", "stuck lofi", "unblocking music"]),
    ("in between things",
     "one chapter ended. the next hasn't started. sitting with the gap.",
     ["transition lofi", "between things lofi", "liminal music", "change lofi"]),
]

AESTHETIC_POOL = [
    # (aesthetic, description, tags_extra)
    ("dark academia",
     "leather notebooks, cold libraries, the smell of old pages",
     ["dark academia lofi", "dark academia music", "academia aesthetic", "library lofi"]),
    ("cottagecore",
     "wildflowers, handwritten recipes, afternoon light through curtains",
     ["cottagecore lofi", "cottagecore music", "cozy lofi", "nature lofi"]),
    ("anime bedroom",
     "posters on the wall, rain outside, this is the scene",
     ["anime lofi", "anime study music", "anime room lofi", "lofi anime"]),
    ("city pop",
     "synthwave haze and neon puddles",
     ["city pop lofi", "city lofi", "urban lofi", "synthwave lofi"]),
    ("cozy builder",
     "building a house in a valley at night",
     ["gaming lofi", "cozy game lofi", "building lofi"]),
    ("vintage library",
     "card catalogues and afternoon light through dusty glass",
     ["vintage lofi", "retro lofi", "library music", "old school lofi"]),
    ("cyberpunk cafe",
     "neon rain and coffee made by a robot",
     ["cyberpunk lofi", "futuristic lofi", "cyber lofi", "neon lofi"]),
    ("botanical study",
     "plants everywhere, green light, earth in the air",
     ["botanical lofi", "nature study music", "plant lofi", "greenhouse lofi"]),
    ("rainy window",
     "the whole world outside is blurred and soft",
     ["rain sounds lofi", "rainy window lofi", "rain music", "rain study music"]),
    ("midnight city",
     "lights below, silence above",
     ["city lights lofi", "midnight city lofi", "rooftop lofi", "city night lofi"]),
    ("cozy cabin",
     "fireplace, pine outside, nowhere to be",
     ["cabin lofi", "cozy cabin music", "fireplace lofi", "mountain lofi"]),
    ("space station",
     "low gravity, stars outside every window",
     ["space lofi", "space music lofi", "astronaut lofi", "galaxy lofi"]),
]

CROSS_GENRE_POOL = [
    # (genre_label, description, tags_extra)
    ("lofi jazz",
     "smoky rooms and brushed snares",
     ["lofi jazz", "jazz lofi", "smooth jazz lofi", "jazz study music"]),
    ("bossa nova lofi",
     "ipanema at 3am, still warm",
     ["bossa nova lofi", "bossa lofi", "brazilian lofi", "bossa nova study"]),
    ("lofi classical",
     "chopin slowed to a heartbeat",
     ["classical lofi", "lofi classical music", "piano lofi", "classical study music"]),
    ("lofi phonk",
     "808s dragging through midnight fog",
     ["lofi phonk", "phonk lofi", "dark phonk lofi", "lofi trap"]),
    ("neo soul lofi",
     "warm rhodes, lazy drums, late-night soul",
     ["neo soul lofi", "soul lofi", "rnb lofi", "smooth lofi"]),
    ("city pop lofi",
     "80s japan. somewhere between disco and dream.",
     ["city pop", "city pop lofi", "japanese city pop", "80s lofi"]),
    ("chillhop",
     "head-nod drums and warm keys",
     ["chillhop", "chillhop music", "chillhop beats", "hip hop lofi"]),
    ("jazz hop",
     "vinyl scratches and saxophone two rooms away",
     ["jazz hop", "jazzhop lofi", "hip hop jazz", "smooth jazzhop"]),
    ("lofi ambient",
     "texture more than melody. presence more than song.",
     ["lofi ambient", "ambient lofi", "ambient study music", "atmospheric lofi"]),
    ("lofi drill",
     "sliding 808s at half time. all the weight, none of the aggression.",
     ["lofi drill", "drill lofi", "chill drill", "uk drill lofi"]),
    ("vaporwave lofi",
     "slowed down. everything softer. nostalgic for things that never happened.",
     ["vaporwave lofi", "aesthetic lofi", "retrowave study music", "90s lofi", "vaporwave beats"]),
    ("lofi house",
     "four on the floor. but quieter. but warmer.",
     ["lofi house music", "house beats study", "deep house lofi", "4/4 lofi", "house lofi"]),
    ("bedroom pop lofi",
     "small, close, a little out of focus. heard like a memory.",
     ["bedroom pop lofi", "indie lofi", "guitar lofi", "diy study music", "bedroom lofi"]),
    ("lofi rnb",
     "old soul records at midnight. muffled through the walls.",
     ["lofi rnb", "soul lofi", "rnb study music", "r&b lofi beats", "neo soul lofi"]),
]

# ──────────────────────────────────────────────────────────────────────────────
#  TITLES  -- the three title forms live in scripts/titles.py
# ──────────────────────────────────────────────────────────────────────────────

HOOK_STRATEGIES = ("scene", "moment", "radio")   # forms in scripts/titles.py


DURATION_DISPLAY = {
    "test":      "10 sec",
    "30 min":    "30 min",
    "45 min":    "45 min",
    "1 hour":    "1 hour",
    "90 min":    "90 min",
    "2 hours":   "2 hours",
    "3 hours":   "3 hours",
    "4 hours":   "4 hours",
    "5 hours":   "5 hours",
    "8 hours":   "8 hours",
    "10 hours":  "10 hours",
    "all night": "all night",
}

# Seconds per duration label (used for dynamic chapter generation)
DURATION_SECS = {
    "test":      30,
    "30 min":    1800,
    "45 min":    2700,
    "1 hour":    3600,
    "90 min":    5400,
    "2 hours":   7200,
    "3 hours":   10800,
    "4 hours":   14400,
    "5 hours":   18000,
    "8 hours":   28800,
    "10 hours":  36000,
    "all night": 28800,
}

# ──────────────────────────────────────────────────────────────────────────────
#  TAG SYSTEM  — broad + mid + long-tail + concept-specific
# ──────────────────────────────────────────────────────────────────────────────

# Tags describe this video only. The old lists named genres the video
# wasn't (phonk, dark, jazz on every upload) and made claims ("study music
# that actually works", "music for anxiety"), which is the irrelevant and
# misleading metadata YouTube's spam policy covers. Tags also carry little
# ranking weight, so a short accurate list costs nothing.
TAGS_GENERIC = [
    "lofi", "lofi beats", "study music", "focus music", "chill music",
    "background music", "lofi for studying", "instrumental",
]
_MAX_TAGS = 18

TAGS_DURATION = {
    "30 min":    ["lofi 30 minutes", "30 minute study session", "quick focus lofi", "short lofi mix"],
    "45 min":    ["lofi 45 minutes", "45 minute study music", "focus session lofi", "one class of lofi"],
    "1 hour":    ["lofi 1 hour", "1 hour study music", "lofi one hour mix", "hour of lofi"],
    "90 min":    ["lofi 90 minutes", "90 minute study mix", "1.5 hour lofi", "hour and a half lofi"],
    "2 hours":   ["lofi 2 hours", "2 hour study music", "lofi two hour mix", "2 hour focus session"],
    "3 hours":   ["lofi 3 hours", "3 hour study music", "long study music", "lofi marathon"],
    "4 hours":   ["lofi 4 hours", "4 hour study music", "marathon study session", "long lofi mix"],
    "5 hours":   ["lofi 5 hours", "5 hour study music", "all day lofi", "extended lofi session"],
    "8 hours":   ["lofi 8 hours", "8 hour study music", "lofi sleep music", "all night study lofi", "8 hour lofi"],
    "10 hours":  ["lofi 10 hours", "10 hour study music", "lofi for sleeping", "lofi all night long", "overnight lofi"],
    "all night": ["all night lofi", "lofi all night", "8 hour study music", "overnight lofi", "lofi sleep music"],
}

# YouTube's Data API rejects (400 invalidTags) any single tag over ~100
# chars even though the only *documented* limit is the 500-char aggregate
# budget build_tags() already enforces below -- confirmed 2026-08-13 when a
# long concept-derived tag tripped this and burned all 5 upload retries on
# a permanently-invalid payload (see upload_youtube.py's retry loop, which
# now also stops retrying on this exact error instead of repeating it).
_MAX_TAG_CHARS = 100


def _clean_tag(t: str) -> str:
    """Strip leading #, angle brackets (YouTube rejects '<'/'>' in tags), and
    collapse spaces — YouTube tags are plain text, and (undocumented but
    consistently enforced) each individual tag must stay under ~100 chars."""
    t = t.lstrip("#").replace("<", "").replace(">", "").strip()
    return t[:_MAX_TAG_CHARS].strip()


# Theme-tied geographic/cultural tags -- deliberately narrow. The concept
# generator bans naming a real city/country in the video's narrative text
# (a video isn't actually "in Tokyo", so claiming that in the description
# would be misleading), but a handful of visual themes carry a real,
# already-established cultural identity through their own aesthetic (the
# neon-signage/rain palette of neon_tokyo, the cherry-blossom imagery of
# sakura_night) -- tagging that identity as a search keyword is different
# from the narrative claiming false specificity, and matches the existing
# precedent of the "city pop" cross-genre pool entry already carrying
# "japanese city pop" as a tag (see CROSS_GENRE_POOL). Only themes with a
# genuinely unambiguous cultural association get an entry here.
_THEME_GEO_TAGS: dict[str, list[str]] = {
    "neon_tokyo":   ["tokyo lofi", "japan aesthetic", "tokyo night lofi"],
    "sakura_night": ["japan aesthetic", "sakura season lofi"],
}


def build_tags(concept: dict, duration: str, theme_name: str | None = None) -> list:
    """At most _MAX_TAGS tags, most specific first: the video's genre, the
    concept's own tags, its length, the theme's tags, then generic ones."""
    genre = (concept.get("genre_label") or "").strip()
    candidates: list[str] = []
    if genre:
        g = search_phrase(genre)
        if g.lower() == "lo-fi hip hop":
            g = "lofi hip hop"   # the spelling people search
        dur = DURATION_DISPLAY.get(duration, duration)
        # How people actually search for a genre: mix, beats, playlist, length.
        candidates += [genre, g, f"{g} mix", f"{g} beats", f"{g} {dur}", f"{g} playlist"]
        if concept.get("activity"):
            candidates.append(f"{g} for {concept['activity']}")
    candidates += [_clean_tag(t) for t in concept.get("tags_extra", []) if t.strip("#")]
    candidates += TAGS_DURATION.get(duration, [])[:2]
    candidates += _THEME_GEO_TAGS.get(theme_name or "", [])
    candidates += TAGS_GENERIC

    seen: set[str] = set()
    out: list[str] = []
    for t in candidates:
        t = t.strip()[:_MAX_TAG_CHARS].strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:_MAX_TAGS]


# ──────────────────────────────────────────────────────────────────────────────
#  DESCRIPTION TEMPLATES
# ──────────────────────────────────────────────────────────────────────────────

DESCRIPTION_HOOKS = [
    "you found this for a reason.",
    "just {duration} of lofi, start to finish.",
    "close the other tabs. This one stays.",
    "for the {activity} sessions that go longer than planned.",
    "{duration} of beats, start to finish.",
    "for the ones still awake at this hour.",
    "nothing to skip, nothing to change. Press play.",
]

# The tracklist (real chapters, one per track) is added once the video is
# assembled and the order is known; see with_tracklist().
DESCRIPTION_BODY = """{search_line}

{mood_hook}

{setting_story}

─────────────────────────────────────
🔔 Subscribe for more lo-fi
👍 Like if this found you at the right time
💬 Tell me what you were working on in the comments

Original music, written and mixed by this channel's own composing software. Drums use free CC0 one-shot samples; no AI models are involved.

{hashtags}"""


def _sentence(text: str) -> str:
    """Capitalise the first letter and end with exactly one full stop."""
    text = (text or "").strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else text + "."


def _build_setting_story(concept: dict) -> str:
    """One or two short sentences: when, the mood, and what it's for. Built
    from whole phrases only, so every combination stays grammatical."""
    # Only time-themed concepts lead with their time; for the others the
    # time label is incidental and can contradict the mood line.
    time_ = (concept.get("time_label") or "") if concept.get("pillar") == "temporal" else ""
    mood = concept.get("mood_line") or ""
    act = concept.get("activity") or "work"
    dur = concept.get("duration") or "an hour"
    use = random.choice([
        f"Good for {act}.",
        f"Put it on for {act}.",
        f"{dur} for {act}, start to finish.",
        f"Made to sit quietly behind {act}.",
    ])
    return " ".join(p for p in (_sentence(time_), _sentence(mood), _sentence(use)) if p)


def _fmt_ts(secs: float) -> str:
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def with_tracklist(description: str, tracks: list[dict]) -> str:
    """Insert a tracklist with each track's real start time. YouTube turns
    it into chapters when there are at least three, starting at 0:00."""
    if not tracks:
        return description
    seen: dict[str, int] = {}
    rows = []
    for t in tracks:
        seen[t["title"]] = seen.get(t["title"], 0) + 1
        n = seen[t["title"]]
        rows.append(f"{_fmt_ts(t['start'])} {t['title']}" + (f" ({n})" if n > 1 else ""))
    lines = "\n".join(rows)
    block = f"TRACKLIST\n{lines}\n\n"
    marker = "─────"
    i = description.find(marker)
    out = description[:i] + block + description[i:] if i != -1 else description + "\n\n" + block
    return out[:4900]


# ──────────────────────────────────────────────────────────────────────────────
#  CONCEPT GENERATION
# ──────────────────────────────────────────────────────────────────────────────

def _pillar_weights() -> dict[str, float]:
    """
    Per-pillar weight multipliers derived from analytics_log.json.
    High-performing pillars get up to 2x weight; low performers get 0.5x.
    Falls back to uniform 1.0 if fewer than 5 samples per pillar exist.

    Thin wrapper kept for pick_concept_from_pool()'s call site -- the real
    implementation is scripts/analytics.py's pillar_weights(), which is now
    backed by Beta-Bernoulli posterior means (scripts/bandit.py)
    over a composite engagement score instead of a raw CTR-ratio multiplier,
    and shares its binarization/posterior-ratio logic with
    duration_weights()/title_variant_weights() instead of each having its
    own hand-rolled copy.
    """
    _PILLARS = ["temporal", "activity", "emotional", "aesthetic", "cross_genre"]
    default: dict[str, float] = {p: 1.0 for p in _PILLARS}
    try:
        from scripts.analytics import pillar_weights as _pillar_weights_impl
        return _pillar_weights_impl(_PILLARS)
    except Exception:
        return default


# Preferred title length band (research: 40-60 characters read fully on
# mobile). A preference when picking among candidates, not a hard limit.
_TITLE_TARGET_MIN, _TITLE_TARGET_MAX = 40, 62

_UPLOAD_LOG = os.path.join(os.path.dirname(__file__), "..", "upload_log.json")


def published_titles() -> set[str]:
    """Titles already on the channel (upload_log.json), so a daily channel
    doesn't post the same title twice."""
    try:
        with open(_UPLOAD_LOG) as f:
            return {e.get("title") for e in json.load(f) if isinstance(e, dict) and e.get("title")}
    except (OSError, ValueError):
        return set()


def generate_title_variants(
    concept: dict,
    duration: str,
    trends: dict | None = None,
    n: int = 3,
    taken: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Up to n distinct titles, one per title form (HOOK_STRATEGIES: scene,
    moment, radio), never one already published (`taken`, default: the
    upload log). Returns (titles, strategies) as parallel lists;
    `strategies[i]` is the form that really built `titles[i]`, so the
    bandit credits the right form.
    """
    taken = published_titles() if taken is None else taken
    variants: list[str] = []
    strategies: list[str] = []

    def _best(strategy: str) -> str | None:
        found = None
        for _attempt in range(12):
            cand = build_title(concept, duration, strategy=strategy, trends=trends)
            if cand in variants or cand in taken:
                continue
            found = found or cand
            if _TITLE_TARGET_MIN <= len(cand) <= _TITLE_TARGET_MAX:
                return cand
        return found

    for i in range(n):
        first = HOOK_STRATEGIES[i % len(HOOK_STRATEGIES)]
        # A form whose few titles are all used falls back to the others.
        for strategy in (first, *[s for s in HOOK_STRATEGIES if s != first]):
            title = _best(strategy)
            if title:
                variants.append(title)
                strategies.append(strategy)
                break
    if not variants:   # every phrase already used: a repeat beats no title
        variants, strategies = [build_title(concept, duration, "scene", trends)], ["scene"]
    return variants, strategies


_SEASON_WORDS = {"winter": (12, 1, 2), "spring": (3, 4, 5), "summer": (6, 7, 8),
                 "autumn": (9, 10, 11), "last day of the year": (12,)}


def _in_season(label: str, month: int | None = None) -> bool:
    """A label naming a season (or New Year's Eve) only fits that time of year."""
    month = month or datetime.datetime.now(datetime.timezone.utc).month
    for word, months in _SEASON_WORDS.items():
        if word in label:
            return month in months
    return True


def _clip_words(text: str, limit: int) -> str:
    """Shorten to `limit` characters without cutting a word in half."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:—-– ")


def pick_concept_from_pool() -> dict:
    """Combinatorial concept from the fallback pools."""
    _pw      = _pillar_weights()
    _pillars = list(_pw.keys())
    pillar   = random.choices(_pillars, weights=[_pw[p] for p in _pillars], k=1)[0]
    act      = random.choice(ACTIVITY_POOL)
    time_  = random.choice([t for t in TIME_POOL if _in_season(t[0])])

    if pillar == "temporal":
        time2 = random.choice([t for t in TIME_POOL if _in_season(t[0])])
        concept = {
            "pillar":      "temporal",
            "concept":     f"{time2[0]} {act[0]} session · {time2[1]}",
            "city":        None,
            "setting":     "your space",
            "time_label":  time2[0],
            "mood_line":   time2[1],
            "activity":    act[0],
            "genre_label": "lo-fi hip hop",
            "aesthetic":   None,
            "tags_extra":  time2[2] + act[2][:2],
        }

    elif pillar == "activity":
        act2 = random.choice(ACTIVITY_POOL)
        concept = {
            "pillar":      "activity",
            "concept":     f"{act2[0]} session — {act2[1]}",
            "city":        None,
            "setting":     "wherever you are",
            "time_label":  time_[0],
            "mood_line":   act2[1],
            "activity":    act2[0],
            "genre_label": "lo-fi hip hop",
            "aesthetic":   None,
            "tags_extra":  act2[2],
        }

    elif pillar == "emotional":
        emo = random.choice(EMOTIONAL_POOL)
        concept = {
            "pillar":      "emotional",
            "concept":     f"lofi for the {emo[0]} — {_clip_words(emo[1], 60)}",
            "city":        None,
            "setting":     "wherever you are",
            "time_label":  time_[0],
            "mood_line":   _clip_words(emo[1], 60),
            "activity":    act[0],
            "genre_label": "lo-fi hip hop",
            "aesthetic":   None,
            "tags_extra":  emo[2],
        }

    elif pillar == "aesthetic":
        aes = random.choice(AESTHETIC_POOL)
        concept = {
            "pillar":      "aesthetic",
            "concept":     f"{aes[0]} · {aes[1]}",
            "city":        None,
            "setting":     aes[0],
            "time_label":  time_[0],
            "mood_line":   aes[1],
            "activity":    act[0],
            "genre_label": "lo-fi hip hop",
            "aesthetic":   aes[0],
            "tags_extra":  aes[2],
        }

    else:  # cross_genre
        cg = random.choice(CROSS_GENRE_POOL)
        concept = {
            "pillar":      "cross_genre",
            "concept":     f"{cg[0]} · {cg[1]}",
            "city":        None,
            "setting":     "any room",
            "time_label":  time_[0],
            "mood_line":   cg[1],
            "activity":    act[0],
            "genre_label": cg[0],
            "aesthetic":   None,
            "tags_extra":  cg[2],
        }

    return concept


def pick_concept(trends: dict | None = None) -> dict:
    """Get a concept from the analytics-weighted procedural pool.

    `trends` is accepted for call-site compatibility and currently unused."""
    return pick_concept_from_pool()


# Maps internal sub_genre keys → SEO genre_label strings used in titles/descriptions.
# Any sub_genre not in this dict falls back to "lo-fi hip hop".
_SUBGENRE_TO_GENRE_LABEL: dict[str, str] = {
    # Each genre under the name people search for it. These feed titles,
    # tags, hashtags and genre playlists; several used to name a different
    # genre (house as "city pop lofi", phonk as "dark lofi", vaporwave as
    # "lofi ambient", anime and piano as "lofi jazz").
    "dark_lofi":      "dark lofi",
    "lofi_phonk":     "lofi phonk",
    "vaporwave":      "vaporwave",
    "ambient":        "ambient lofi",
    "lofi_jazz":      "lofi jazz",
    "jazz_cafe":      "jazz cafe lofi",
    "nujabes":        "jazz hop",
    "neo_soul":       "neo soul lofi",
    "bossa_lofi":     "bossa nova lofi",
    "lofi_rnb":       "r&b lofi",
    "chillhop":       "chillhop",
    "hip_hop_lofi":   "lo-fi hip hop",
    "lo_fi_funk":     "lofi funk",
    "chill_beats":    "chill lofi beats",
    "lofi_house":     "lofi house",
    "cozy_cafe":      "cafe lofi",
    "morning_lofi":   "morning lofi",
    "anime_lofi":     "anime lofi",
    "summer_vibes":   "summer lofi",
    "bedroom_pop":    "bedroom pop",
    "city_pop":       "city pop lofi",
    "study_lofi":     "lo-fi hip hop",
    "piano_lofi":     "piano lofi",
    "lofi_classical": "classical lofi",
    "sleep_lofi":     "sleep lofi",
    "lofi_garage":    "lofi garage",
    "lofi_synthwave": "synthwave lofi",
    "lofi_drill":     "lofi drill",
    "lofi_world":     "indian lofi",
}


def concept_from_music_params(music_sub_genre: str, music_mood: str, base_concept: dict) -> dict:
    """
    Return a copy of base_concept with genre_label and mood_line overridden
    to match what was actually generated. Called after generate_tracks() so
    SEO titles reflect the real music, not the pre-generation guess.

    A "cross_genre" concept keeps its own wording ("lofi ambient", "vaporwave
    lofi") when the music really is that genre; when the music turned out to
    be something else, the label is replaced, because a title must never name
    a genre that doesn't play.
    """
    updated = dict(base_concept)
    genre_label = _SUBGENRE_TO_GENRE_LABEL.get(music_sub_genre)
    if base_concept.get("pillar") == "cross_genre":
        from scripts.composer import _resolve_genre_hint
        if _resolve_genre_hint(base_concept.get("genre_label") or "") == music_sub_genre:
            genre_label = None
    if genre_label:
        updated["genre_label"] = genre_label
    if music_mood and len(music_mood.split()) >= 3:
        updated["mood_line"] = music_mood
    return updated


# ──────────────────────────────────────────────────────────────────────────────
#  TITLE BUILDER
# ──────────────────────────────────────────────────────────────────────────────

_THUMB_TEXT: dict[str, str] = {}   # title -> the short phrase its thumbnail shows


def build_title(concept: dict, duration: str, strategy: str | None = None,
                 trends: dict | None = None) -> str:
    """One title in one of the HOOK_STRATEGIES forms (see scripts/titles.py):
    "scene" ("rain on the window 🌧️ [lofi hip hop · 1 hour]"), "moment"
    ("reading after midnight ☕ [lofi jazz · 1 hour]") or "radio" ("lofi hip
    hop 🌧️ rainy beats to study & relax to"). An unknown strategy picks one."""
    from scripts import titles
    if strategy not in HOOK_STRATEGIES:
        strategy = random.choice(HOOK_STRATEGIES)
    title, thumb = titles.build(
        strategy,
        theme=concept.get("theme") or "cozy_rain",
        genre=concept.get("genre_label") or "lo-fi hip hop",
        activity=(concept.get("activity") or "studying").lower(),
        duration=DURATION_DISPLAY.get(duration, duration),
        trends=trends,
    )
    _THUMB_TEXT[title] = thumb
    return title


# ──────────────────────────────────────────────────────────────────────────────
#  DESCRIPTION BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def search_phrase(genre: str) -> str:
    """The genre as people type it into search: always with "lofi" in it."""
    genre = (genre or "lofi").strip()
    return genre if re.search(r"lo-?fi", genre, re.I) else f"{genre} lofi"


def _search_line(genre: str, duration: str, activity: str) -> str:
    """The first line YouTube shows under the title in search results: what
    the video is, how long, and what it's for, in the words people search."""
    uses = []
    for u in (activity, "studying", "working", "relaxing"):
        if u and u.lower() not in uses:
            uses.append(u.lower())
    uses = uses[:3]
    use_text = f"{', '.join(uses[:-1])} and {uses[-1]}" if len(uses) > 1 else uses[0]
    return _sentence(f"{duration} of {search_phrase(genre)} beats for {use_text}")


def build_description(concept: dict, duration: str) -> str:
    activity = concept.get("activity", "work")
    genre    = concept.get("genre_label", "lo-fi hip hop")

    concept_ctx = dict(concept)
    concept_ctx["duration"] = DURATION_DISPLAY.get(duration, duration)

    mood_hook = random.choice(DESCRIPTION_HOOKS).format(**concept_ctx)
    mood_hook = mood_hook[0].upper() + mood_hook[1:]
    setting_story = _build_setting_story(concept_ctx)

    # Hashtags: the first three show above the title, so they must describe
    # this video: lofi, its actual genre, its length. No duplicates.
    dur_tags = TAGS_DURATION.get(duration, [])
    candidates = ["lofi", _clean_tag(genre).replace(" ", ""),
                  _clean_tag(dur_tags[0]).replace(" ", "") if dur_tags else "",
                  "studymusic"]
    hashtags, seen = [], set()
    for h in candidates:
        if h and h not in seen and re.fullmatch(r"\w+", h):
            seen.add(h)
            hashtags.append(f"#{h}")

    desc = DESCRIPTION_BODY.format(
        search_line=_search_line(genre, DURATION_DISPLAY.get(duration, duration), activity),
        mood_hook=mood_hook,
        setting_story=setting_story,
        hashtags=" ".join(hashtags[:4]),
    )
    return desc.strip()[:4900]   # YouTube's limit is 5000; the tracklist goes in later


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def generate_seo(theme_name: str = None, duration: str = None,
                 concept: dict = None,
                 trends: dict | None = None) -> tuple:
    """
    Generate SEO metadata for a video.

    Args:
        theme_name: Visual theme (cozy_rain, purple_dusk, etc.)
        duration:   Video duration label ("1 hour", "2 hours", etc.)
        concept:    Pre-generated concept dict (pass from run.py so the title,
                    visual and music all describe the same concept)
        trends:     TrendSnapshot from trend_research.get_trend_snapshot()

    Returns: (seo_dict, seo_file_path)
    """
    duration = duration or "2 hours"

    # Get or generate concept (trend-aware)
    if concept is None:
        print("  [SEO] Generating concept...")
        concept = pick_concept(trends)

    # Three title variants, one per form (scene, moment, radio); one is
    # picked, weighted by two bandit signals multiplied together: past
    # performance of each form for this pillar (title_variant_weights) and
    # of surface features such as length (title_feature_weights). Both are
    # a neutral 1.0 until a form or feature has >=5 scored videos.
    concept = {**concept, "theme": theme_name or concept.get("theme") or "cozy_rain"}
    title_variants, variant_strategies = generate_title_variants(concept, duration, trends, n=3)
    from scripts.analytics import (
        title_variant_weights as _title_variant_weights,
        title_feature_weights as _title_feature_weights_fn,
        title_features as _title_features_fn,
    )
    _tvw = _title_variant_weights().get(concept.get("pillar"), {})
    _tfw = _title_feature_weights_fn()

    def _feature_weight(title: str) -> float:
        w = 1.0
        for dim, bucket in _title_features_fn(title).items():
            w *= _tfw.get(dim, {}).get(bucket, 1.0)
        return w

    _weights = [
        _tvw.get(s, 1.0) * _feature_weight(t)
        for s, t in zip(variant_strategies, title_variants)
    ]
    chosen_idx        = random.choices(range(len(title_variants)), weights=_weights, k=1)[0]
    title             = title_variants[chosen_idx]
    chosen_strategy   = variant_strategies[chosen_idx] if chosen_idx < len(variant_strategies) else None
    description = build_description(concept, duration)
    tags        = build_tags(concept, duration, theme_name=theme_name)

    # Other channels' trending tags are not copied in: the old keyword filter
    # let through anything containing "music", including other artists' and
    # channels' names.

    _now_utc = datetime.datetime.now(datetime.timezone.utc)
    ts = _now_utc.strftime("%Y%m%d_%H%M%S")
    # Unique ref stamped into description — used for cross-device duplicate detection.
    # YouTube search doesn't support description search, so we list recent videos and
    # grep descriptions ourselves. It is visible, as the last line of the description.
    ref_id = f"lofi:{ts}_{secrets.token_hex(2)}"
    description = description.rstrip() + f"\n\n{ref_id}"

    seo = {
        "title":            title,
        "description":      description,
        "tags":             tags,
        "category_id":      "10",       # Music
        "privacy":          "public",
        "made_for_kids":    False,
        "theme":            theme_name or "cozy_rain",
        "duration":         duration,
        "concept":          concept.get("concept", ""),
        "pillar":           concept.get("pillar", "temporal"),
        "mood":             concept.get("mood_line", ""),
        "city":             concept.get("city"),
        "activity":         concept.get("activity", ""),
        "genre_label":      concept.get("genre_label", ""),
        "thumb_text":       _THUMB_TEXT.get(title, ""),
        "generated_at":     _now_utc.isoformat(),
        "ref_id":           ref_id,
        "title_variants":           title_variants,
        "title_variant_strategies": variant_strategies,
        "title_chosen_idx":         chosen_idx,
        "title_chosen_strategy":    chosen_strategy,
    }
    out_path = os.path.join(ASSETS_DIR, f"seo_{ts}.json")
    with open(out_path, "w") as f:
        json.dump(seo, f, indent=2, ensure_ascii=False)

    print(f"[SEO] concept: {concept.get('concept', '')[:70]}")
    print(f"[SEO] title:   {title}")
    print(f"[SEO] tags ({len(tags)}): {', '.join(tags[:6])}...")
    print(f"[SEO] saved:   {out_path}")
    return seo, out_path


if __name__ == "__main__":
    import sys
    theme    = sys.argv[1] if len(sys.argv) > 1 else None
    duration = sys.argv[2] if len(sys.argv) > 2 else "2 hours"
    seo, path = generate_seo(theme, duration)
    print("\n--- CONCEPT ---")
    print(seo["concept"])
    print("\n--- TITLE ---")
    print(seo["title"])
    print("\n--- DESCRIPTION ---")
    print(seo["description"])
    print("\n--- TAGS ---")
    print(seo["tags"])
