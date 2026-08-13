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
  · Description (narrative paragraph + chapters + CTA)
  · Tags (broad + mid + long-tail + concept-specific)
  · Chapter labels matching the concept narrative

Groq generates the concept when available. 300+ fallback pool ensures
variety even without API access.

Output: assets/seo_TIMESTAMP.json
"""

import os, json, random, datetime, secrets, re

from scripts.seo_utils import format_timestamp as _secs_to_ts

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets')
os.makedirs(ASSETS_DIR, exist_ok=True)



GROQ_KEY      = os.getenv('GROQ_API_KEY')
GEMINI_KEY    = os.getenv('GEMINI_API_KEY')
GEMINI_BACKUP = os.getenv('GEMINI_API_KEY_BACKUP')

# ──────────────────────────────────────────────────────────────────────────────
#  CONCEPT POOLS  (fallback when Groq/Gemini is unavailable)
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
    ("minecraft cozy",
     "building a house in a valley at night",
     ["minecraft lofi", "gaming lofi", "minecraft music", "building lofi"]),
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
     "d'angelo never left. this is his ghost.",
     ["neo soul lofi", "soul lofi", "rnb lofi", "smooth lofi"]),
    ("city pop lofi",
     "80s japan. somewhere between disco and dream.",
     ["city pop", "city pop lofi", "japanese city pop", "80s lofi"]),
    ("chillhop",
     "the genre that named the feeling",
     ["chillhop", "chillhop music", "chillhop beats", "hip hop lofi"]),
    ("jazz hop",
     "vinyl scratches and saxophone two rooms away",
     ["jazz hop", "jazzhop lofi", "hip hop jazz", "smooth jazzhop"]),
    ("lofi ambient",
     "texture more than melody. presence more than song.",
     ["lofi ambient", "ambient lofi", "ambient study music", "atmospheric lofi"]),
    ("lofi trap",
     "808 at 70bpm. all the weight, none of the aggression.",
     ["lofi trap", "trap lofi", "slow trap", "chill trap"]),
    ("vaporwave lofi",
     "slowed down. everything softer. nostalgic for things that never happened.",
     ["vaporwave lofi", "aesthetic lofi", "retrowave study music", "90s lofi", "vaporwave beats"]),
    ("lofi house",
     "four on the floor. but quieter. but warmer.",
     ["lofi house music", "house beats study", "deep house lofi", "4/4 lofi", "house lofi"]),
    ("bedroom pop lofi",
     "recorded in a bedroom. heard like a memory.",
     ["bedroom pop lofi", "indie lofi", "guitar lofi", "diy study music", "bedroom lofi"]),
    ("lofi rnb",
     "al green at midnight. muffled through the walls.",
     ["lofi rnb", "soul lofi", "rnb study music", "r&b lofi beats", "neo soul lofi"]),
]

# ──────────────────────────────────────────────────────────────────────────────
#  TITLE TEMPLATES  (100+ combinations guaranteed per concept)
# ──────────────────────────────────────────────────────────────────────────────

# Title patterns — varied structure, duration placement, separators, and story-first hooks
# Rule: "lofi", "lo-fi", or "study music" must appear within the first 35 characters.
# Vary the skeleton: don't always use [keyword] · {duration} · [thing].


TITLE_PATTERNS_TEMPORAL = [
    # Duration at end
    "lofi hip hop · it's {time} and you're still awake — {duration}",
    "study music · {time}, the deadline blinked first — {duration} 📚",
    "lofi · {time}, headphones in, world out — {duration} 🎵",
    # Parenthetical
    "lofi hip hop · {time} focus (the {activity} kind) — {duration}",
    "study music · {time} — one more hour ({duration})",
    # Comma chain
    "lofi hip hop, {time}, still {activity}, {duration}",
    # Observation with twist
    "lofi · {duration} — started at {time}, forgot to stop",
    "study lofi · {time} hits different when you're finally {activity} · {duration}",
    # Short/punchy
    "lofi hip hop · {time} · {duration} · go",
    "lofi · {time}, no sleep, {duration} to go 🌙",
]

TITLE_PATTERNS_ACTIVITY = [
    # Duration at end
    "lofi hip hop · put this on, start {activity}, check back in {duration}",
    "study music · {activity} until it clicks — {duration} 📚",
    "lofi · headphones on, {activity} open, timer set — {duration}",
    # Parenthetical
    "lofi hip hop · you said five more minutes ({duration} ago)",
    "study music · the {activity} session that actually worked ({duration}) 🎵",
    # Action-first
    "lofi hip hop · {duration} · close the other tabs, {activity}",
    "lofi · {duration} · {activity} now, everything else later",
    # Understated
    "study lofi · {duration} of {activity}, no commentary",
    "lofi hip hop · {duration} · {activity}. that's it. that's the video.",
    # Question turned statement
    "lofi · {duration} · what if you just {activity} for the whole thing 🎧",
]

TITLE_PATTERNS_EMOTIONAL = [
    # Duration at end — emotion leads
    "lofi hip hop · {emotional_state} but the cursor is moving again — {duration}",
    "study music · for the {emotional_state} ones still at their desk — {duration} 🌙",
    "lofi · {emotional_state} and somehow still {activity} — {duration}",
    # Parenthetical
    "lofi hip hop · some nights are {emotional_state} ({duration} to get through it)",
    "study music · you're {emotional_state} and that's fine ({duration}) 🎵",
    # Short and honest
    "lofi hip hop · {duration} · {emotional_state}. working anyway.",
    "lofi · {duration} · {emotional_state} nights deserve good music",
    # Understated empathy
    "study lofi · {duration} · nobody has to know it was a {emotional_state} day",
    "lofi hip hop · {duration} · the {emotional_state} kind of productive",
    # Specific
    "lofi · {duration} · {emotional_state} at {time} is its own thing 🌙",
]

TITLE_PATTERNS_AESTHETIC = [
    # Duration at end
    "lofi hip hop · {aesthetic} light, {activity} open, timer running — {duration}",
    "study music · {aesthetic} energy study block — {duration} 📚",
    "lofi · {aesthetic} room, {aesthetic} playlist, see what happens — {duration}",
    # Parenthetical
    "lofi hip hop · {aesthetic} focus session ({duration}, no breaks)",
    "study lofi · the {aesthetic} {activity} arc ({duration}) 🎵",
    # Minimal
    "lofi hip hop · {aesthetic} · {duration}",
    "lofi · {aesthetic}, {activity}, {duration} 🌙",
    # Wry observation
    "study music · {duration} · {aesthetic} aesthetic, actual productivity",
    "lofi hip hop · {duration} · turns out {aesthetic} helps you focus",
    "lofi · {duration} · {aesthetic} era, {activity} grind 📚",
]

TITLE_PATTERNS_CROSSGENRE = [
    # Duration at end — concept leads
    "lofi hip hop · what if {genre} never left the library — {duration}",
    "study music · {genre} roots, lofi filter, {activity} session — {duration} 🎵",
    "lofi · {genre} but quieter, {duration} to {activity}",
    # Parenthetical
    "lofi hip hop · the {genre} {activity} playlist ({duration})",
    "study lofi · {genre} without the crowd ({duration}) 📚",
    # Minimal
    "lofi hip hop · {genre} · {duration}",
    "{genre} lofi · {duration} · {activity} 🌙",
    # Observation
    "lofi hip hop · {duration} · {genre} never sounded this focused",
    "study music · {duration} · {genre} energy, library quiet",
    "lofi · {duration} · {genre} fan? this one's for you 🎵",
]

# Duration display strings — shown in titles and descriptions
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
#  CHAPTER SETS  — narrative-aware labels per duration
# ──────────────────────────────────────────────────────────────────────────────

def _build_chapters(duration: str, concept: dict) -> list:
    """Dynamically compute chapter timestamps and narrative labels for any duration."""
    total = DURATION_SECS.get(duration, 7200)
    city  = concept.get("city", "")
    time_ = concept.get("time_label", "")

    # Chapter labels are indexed by YouTube search — mix atmospheric + keyword phrases
    # so a single upload can rank for multiple long-tail queries
    intros = [
        "lofi study session begins", "signal found · lo-fi",
        f"{city.lower()} lofi — signal found" if city else "lofi intro · tune in",
        "lo-fi beats start here", "ambient swell · lofi hip hop",
        "tuning in · study music", "frequencies align · chill beats",
    ]
    mids_a = [
        "deep focus · lofi study", "flow state · lo-fi beats",
        "lofi hip hop · locked in", "study music · full send",
        f"{time_.lower()} lofi — deep focus" if time_ else "midnight lofi · deep focus",
        "concentration zone · lofi", "lofi beats · momentum builds",
    ]
    mids_b = [
        "second wind · study lofi", "still studying · lo-fi mix",
        "lofi chill · hours disappear", "focus music · still going",
        "ambient lofi · groove settles", "eyes on the page · lofi",
    ]
    peaks = [
        "peak focus · lofi hip hop", "hyperfocus · study music",
        "deep session · lo-fi beats", "lofi marathon · wired in",
        "flow state peak · chill music", "no turning back · lofi",
    ]
    night_markers = [
        "midnight study · lofi", "3am lofi drift",
        "late night study music", "pre-dawn · lo-fi static",
        "4am study session · lofi", "the dark hours · chill beats",
    ]
    outros = [
        "session ends · lofi fade", "last lofi beat · fade out",
        "study session complete", "fade to static · lofi outro",
        "morning creeps in · lo-fi", "signal fades · rest",
    ]

    # Pick chapter count and time fractions based on total length
    if total <= 2700:       # ≤45 min → 4 chapters
        fracs  = [0.00, 0.15, 0.55, 0.92]
        labels = [
            random.choice(intros),
            random.choice(mids_a),
            random.choice(mids_b),
            random.choice(outros),
        ]
    elif total <= 5400:     # ≤90 min → 5 chapters
        fracs  = [0.00, 0.08, 0.32, 0.68, 0.93]
        labels = [
            random.choice(intros),
            random.choice(mids_a),
            random.choice(mids_b),
            "winding down",
            random.choice(outros),
        ]
    elif total <= 10800:    # ≤3 hours → 6 chapters
        fracs  = [0.00, 0.05, 0.28, 0.52, 0.78, 0.96]
        labels = [
            random.choice(intros),
            random.choice(mids_a),
            random.choice(mids_b),
            random.choice(peaks),
            "late push",
            random.choice(outros),
        ]
    else:                   # 4h+ → 7 chapters; use atmospheric night-time markers
        fracs  = [0.00, 0.04, 0.20, 0.38, 0.57, 0.78, 0.94]
        labels = [
            random.choice(intros),
            random.choice(mids_a),
            random.choice(mids_b),
            random.choice(night_markers),
            random.choice(peaks),
            "pre-dawn" if total >= 14400 else "late push",
            random.choice(outros),
        ]

    chapters = []
    for frac, label in zip(fracs, labels):
        raw = int(total * frac)
        # Round to nearest minute (except the mandatory 0:00 start)
        secs = 0 if raw == 0 else max(60, (raw // 60) * 60)
        chapters.append((_secs_to_ts(secs), label))
    return chapters

# ──────────────────────────────────────────────────────────────────────────────
#  TAG SYSTEM  — broad + mid + long-tail + concept-specific
# ──────────────────────────────────────────────────────────────────────────────

TAGS_BROAD = [
    # Order matters — first tag is the primary keyword signal for YouTube
    "lofi hip hop", "study music", "lofi", "lofi beats", "chillhop",
    "chill music", "focus music", "relaxing music",
    "background music", "ambient music", "lo-fi",
]

TAGS_MID = [
    "lofi study beats", "lofi chill mix", "lofi hip hop mix",
    "ambient lofi", "lofi jazz", "lofi phonk", "dark lofi",
    "aesthetic lofi", "bedroom lofi", "cozy lofi", "rain lofi",
    "night lofi", "lofi for focus", "lofi for studying",
]

TAGS_LONGTAIL = [
    "lofi music to study and relax to",
    "chill beats to study to",
    "lofi hip hop radio beats to study to",
    "music for concentration and focus",
    "study music with rain sounds",
    "late night study music",
    "lofi for focus and productivity",
    "background music for studying",
    "calm music for anxiety and stress",
    "lo fi hip hop beats",
    "music to help you focus",
    "lofi beats no copyright",
    "lofi music for work from home",
    "best lofi music 2026",
    "lofi playlist for studying 2026",
    "music that feels like a hug",
    "lofi for the overstimulated brain",
    "study music that actually works",
    "background lofi for long sessions",
    "lofi for night owls",
]

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

def _clean_tag(t: str) -> str:
    """Strip leading # and collapse spaces — YouTube tags are plain text."""
    return t.lstrip("#").strip()


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
    # Strategy: maximize the 500-char YouTube tag budget for new-channel discoverability.
    # YouTube has NO individual tag character limit — fill the full 500-char budget.
    # More tag surface = more search entry points = more impressions on a new channel.
    raw_extra = [_clean_tag(t) for t in concept.get("tags_extra", []) if t.strip("#")]

    # Build ordered candidate list: broad first (primary keyword signal), then widen
    candidates: list[str] = []

    # 1. All broad tags — primary keyword must be first for YouTube ranking signal
    candidates += TAGS_BROAD

    # 2. All duration-specific intent tags
    candidates += TAGS_DURATION.get(duration, [])

    # 3. All concept-specific tags from concept generator
    candidates += raw_extra

    # 3b. Theme-tied geographic/cultural tags, if this theme has an entry
    candidates += _THEME_GEO_TAGS.get(theme_name or "", [])

    # 4. Shuffled mid-tier tags for genre variety
    mid_shuffled = TAGS_MID[:]
    random.shuffle(mid_shuffled)
    candidates += mid_shuffled

    # 5. Shuffled long-tail phrases — high value for new-channel search discovery
    longtail_shuffled = TAGS_LONGTAIL[:]
    random.shuffle(longtail_shuffled)
    candidates += longtail_shuffled

    # Dedupe and fill up to 490 chars (YouTube hard limit is 500; 10-char buffer)
    seen: set[str] = set()
    out: list[str] = []
    total_chars = 0
    for t in candidates:
        tl = t.lower()
        char_cost = len(t) + (1 if out else 0)   # +1 for the comma separator
        if tl not in seen and total_chars + char_cost <= 490:
            seen.add(tl)
            out.append(t)
            total_chars += char_cost
    return out

# ──────────────────────────────────────────────────────────────────────────────
#  DESCRIPTION TEMPLATES
# ──────────────────────────────────────────────────────────────────────────────

DESCRIPTION_HOOKS = [
    # Atmospheric/story hooks
    "{mood_line}",
    "{city_phrase}.",
    "you found this for a reason.",
    "no ads. no interruptions. just {duration} of lofi frequencies.",
    "{time_phrase}. {mood_line}.",
    "close the other tabs. this one stays.",
    "for the {activity} sessions that go longer than planned.",
    "{duration} of uninterrupted beats. that's the promise.",
    "signal found. tuning in.",
    "ambient transmission from somewhere soft.",
    "the frequency is always on.",
    "{city_phrase}. {time_phrase}.",
    "for the ones still awake at this hour.",
    "{mood_line}. here's {duration}.",
]

DESCRIPTION_BODY = """
lo-fi hip hop · {duration} for {activity} · no ads, no interruptions.

{mood_hook}

{setting_story}

⏱ CHAPTERS
{chapters}

─────────────────────────────────────
🔔 New lo-fi drops weekly — subscribe if this helped
👍 Like if this found you at the right time
💬 Tell me what you were working on in the comments

Original compositions. All tracks generated fresh for this session.

#lofi #lofihiphop #{tag1} #{tag2} #{tag3}"""


def _strip_leading_article(s: str) -> str:
    """Remove a/an/the from start so templates can add their own article."""
    for art in ("the ", "an ", "a "):
        if s.lower().startswith(art):
            return s[len(art):]
    return s


def _build_setting_story(concept: dict) -> str:
    """Generate a 1-2 sentence scene-setter unique to this concept."""
    city    = concept.get("city")
    time_   = concept.get("time_label")
    setting = _strip_leading_article(concept.get("setting") or "")  or concept.get("setting")
    mood    = concept.get("mood_line", "")
    act     = concept.get("activity", "work")

    m = mood.capitalize() + '.' if mood else ''
    dur = concept.get('duration', '2 hours')
    templates = []

    if city and time_ and setting:
        templates += [
            f"Imagine: a {setting} in {city}, {time_}. {m} Just you, your {act}, and this.",
            f"It's {time_} somewhere in {city}. The {setting} is quiet. This is your background.",
            f"{city}, {time_}. The {setting} hums. You've got {act} to finish. This stays on.",
            f"A {setting} in {city} at {time_}. {m} {dur} of uninterrupted focus.",
            f"You're in a {setting} in {city}. It's {time_}. Nothing else matters right now.",
            f"{city} has a specific energy at {time_}. This was made for that exact moment.",
            f"The {setting} in {city} at {time_} — that's the vibe. {m}",
            f"Turn this on. Find a {setting} in {city}. Let {time_} do the rest.",
            f"{time_.capitalize()} in {city}. You've got {act}. The {setting} has you.",
            f"For every {act} session that started at {time_} in a {setting} in {city}.",
        ]
    elif city and time_:
        templates += [
            f"{city} at {time_}. {m} {dur} to stay in it.",
            f"Something about {city} at {time_} hits different. Here's the soundtrack.",
            f"{time_.capitalize()} in {city}. Put this on. Don't overthink it.",
            f"Built for {city} {time_} sessions. {m}",
            f"It's {time_} in {city} and you need this.",
            f"{city}, {time_}. {m} That's it. That's the description.",
        ]
    elif city and setting:
        templates += [
            f"A {setting} in {city}. {m} {dur} of this.",
            f"The {setting} energy in {city} — captured. {m}",
            f"For {act} in a {city} {setting}. Nothing more, nothing less.",
        ]
    elif city:
        templates += [
            f"{city} has a particular energy. This is made for it.",
            f"Somewhere in {city}, someone is still awake. Here's their playlist.",
            f"Built for {city}. {m} {dur} of lofi that fits.",
            f"If {city} had a sound for {act}, this would be it.",
            f"{city} {act} sessions deserve a proper soundtrack. Here it is.",
            f"For the people in {city} who stay up to get things done.",
        ]
    elif time_ and setting:
        templates += [
            f"A {setting} at {time_}. {m} {dur} of focus.",
            f"{time_.capitalize()}. A {setting}. Your {act}. This.",
            f"The {setting} at {time_} hits different. {m}",
        ]
    elif time_:
        templates += [
            f"{time_.capitalize()}. {m} Here's {dur} of lofi to carry you through.",
            f"The {time_} crowd knows. Made for {act} sessions that refuse to end.",
            f"{time_.capitalize()} {act} sessions have a specific texture. This is it.",
            f"Put this on at {time_}. See what happens to your {act}.",
            f"For {time_} workers who need a soundtrack, not a distraction.",
            f"{m} {time_.capitalize()} energy, {dur} long.",
        ]
    elif setting:
        templates += [
            f"The {setting} vibe — captured. {m} {dur} of this.",
            f"Built for {setting} {act} sessions. {m}",
            f"Everything a {setting} should sound like.",
        ]
    else:
        templates += [
            f"A lo-fi session for your {act}. {m}",
            f"Beats that disappear into the background so your focus can come to the foreground.",
            f"{m} {dur} of lofi. Your {act} will thank you.",
            f"No algorithm. No playlist filler. Just {dur} of focused lofi.",
            f"For {act} that needs a soundtrack without the distraction.",
            f"The background that doesn't compete with what's in the foreground. {m}",
        ]

    return random.choice(templates) if templates else ""


# ──────────────────────────────────────────────────────────────────────────────
#  CONCEPT GENERATION
# ──────────────────────────────────────────────────────────────────────────────

def _build_concept_prompt(trends: dict | None = None) -> str:
    """Build the Groq concept prompt, optionally enriched with live trend data."""
    trend_block = ""
    if trends:
        titles = trends.get("trending_titles", [])[:8]
        season = trends.get("season", "")
        s_kw   = trends.get("seasonal_keywords", [])[:3]
        groq_a = trends.get("groq_analysis", "")
        gemini = trends.get("gemini_insight", "")

        if titles:
            trend_block += f"\nCURRENT TRENDS (use for inspiration — do NOT copy):\n"
            trend_block += f"Season: {season}. Seasonal searches: {', '.join(s_kw)}.\n"
            trend_block += "Top-performing titles this week:\n"
            for t in titles:
                trend_block += f"  • {t[:80]}\n"
        if groq_a:
            trend_block += f"\nStrategic analysis of what's working:\n{groq_a[:400]}\n"
        elif gemini:
            trend_block += f"\nWeb trend insight:\n{gemini[:300]}\n"
        if trend_block:
            trend_block += (
                "\nYour concept should be FRESH — tap into the emotional need these titles serve "
                "but take it somewhere new. What are listeners ACTUALLY searching for that nobody's made yet?\n"
            )

    return f"""\
You are a lo-fi YouTube channel writer. Generate one unique video concept — a place, moment, or feeling that anchors 1-3 hours of music.
{trend_block}
TARGET EMOTIONAL REGISTER: "productive melancholy" — tired, a little sad, but still working. Soft enough to exist in. Heavy enough to mean something. Think: desk lamp at 3am, rain you didn't plan for, a city that doesn't know your name yet.

GENRE DIVERSITY — pick one that fits the concept organically, then build the setting around it:
- "lo-fi hip hop": urban bedroom, city windows at night, headphones as armor against the world
- "lofi jazz": late-night bar after last call, dimly lit practice room, cigarette smoke and brushed snares
- "chillhop": sunny afternoon that asks nothing of you, café terrace, the slow hours between things
- "bossa nova lofi": coastal city, open window, warm breeze and old vinyl scratching
- "neo-soul lofi": Sunday morning, kitchen radio, something cooking, groove with a soft ache in it
- "lofi ambient": liminal spaces, fog, transit — nowhere and everywhere, the mind going quiet
- "city pop lofi": 80s Japan nostalgia, neon reflections on wet asphalt, night drives, cassette tape warmth
- "dark lofi": late and heavy, the hours you wouldn't explain to anyone, cinematic weight

GOOD concepts — specific moment or story, someone can picture exactly where they are:
- "finishing something you started two years ago, alone, past midnight"
- "rain on a window you've watched from desks in four different apartments"
- "the hour after the deadline passes and the silence feels unfamiliar"
- "Sunday neo-soul morning, headphones in, watching the street wake up slowly"
- "4am, still here, the kind of tired that clarifies everything"
- "the playlist you'd make if you knew nobody would hear it"

BAD concepts — NEVER generate these:
- "soft rain on wooden roofs" (noun + adjective, no story, no person, no ache)
- "cozy study vibes" (aesthetic label, not a moment)
- "rainy night lofi" (genre description, not a concept)
- "peaceful evening studying" (generic, no specificity, no tension)
- ANY concept naming a city, country, neighborhood, or real-world location (no Tokyo, Paris, Brooklyn, etc.)

Output ONLY valid JSON:
{{
  "pillar": "emotional",
  "concept": "one-sentence story or moment (max 90 chars)",
  "city": null,
  "setting": "specific place or general setting — NO city or country names",
  "time_label": "exact time or occasion — never just 'night' or 'evening'",
  "mood_line": "one line that IS the feeling — write like a poet, not a marketer (max 70 chars, no period)",
  "activity": "what the listener is doing — specific enough to picture (not just 'studying')",
  "genre_label": "lofi sub-genre label",
  "aesthetic": "aesthetic tag or null",
  "tags_extra": ["5 specific searchable tags unique to THIS concept"]
}}

Rules:
- pillar: one of "temporal","activity","emotional","aesthetic","cross_genre" — NEVER "geographic"
- city: always null — do NOT name any city, country, or place
- concept: evokes a MOMENT not a category, NO location names
- mood_line: the feeling itself in words. AVOID: "for the study sessions", "chill beats for X". DO: "still here, still going", "softer than grief, louder than silence", "the whole world is asleep except you", "for the hours that don't belong to anyone"
- activity: specific enough to picture — "coding a side project", "drawing what you're afraid to show anyone", "writing a letter you won't send", not just "working"
- genre_label: one of "lo-fi hip hop","lofi jazz","chillhop","bossa nova lofi","neo-soul lofi","lofi ambient","city pop lofi","dark lofi"
- tags_extra: 5 searchable tags specific to this concept, not generic "lofi study"
- Be creative. Vary pillars. Output ONLY JSON.
"""


def pick_concept_groq(trends: dict | None = None) -> dict | None:
    """Use Groq to generate a unique video concept, enriched with live trend data."""
    if not GROQ_KEY:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)
        prompt = _build_concept_prompt(trends)

        # Inject a random 'Creative Seed' to force LLM to break from cached patterns
        creative_seed = random.randint(0, 1000000)
        prompt += f"\n\n[CREATIVE SEED: {creative_seed}]\n"
        prompt += "Use this seed to explore a completely different creative direction than previous runs."

        resp   = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.1,
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```"))
        s, e = raw.find("{"), raw.rfind("}") + 1
        concept = json.loads(raw[s:e])
        concept.setdefault("genre_label", "lo-fi hip hop")
        concept.setdefault("tags_extra",  [])
        concept.setdefault("city",        None)
        concept.setdefault("aesthetic",   None)
        print(f"  [Groq] concept: {concept.get('concept', '')[:80]}")
        return concept
    except Exception as ex:
        print(f"  [Groq concept] failed ({ex}), using pool")
        return None


def pick_concept_gemini(trends: dict | None = None) -> dict | None:
    """Use Gemini to generate a unique video concept — primary generator."""
    for key in [GEMINI_KEY, GEMINI_BACKUP]:
        if not key:
            continue
        try:
            from google import genai
            client = genai.Client(api_key=key)
            prompt = _build_concept_prompt(trends)

            # Inject a random 'Creative Seed' to force LLM to break from cached patterns
            creative_seed = random.randint(0, 1000000)
            prompt += f"\n\n[CREATIVE SEED: {creative_seed}]\n"
            prompt += "Use this seed to explore a completely different creative direction than previous runs."

            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            raw = resp.text.strip()
            if "```" in raw:
                raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```"))
            s, e = raw.find("{"), raw.rfind("}") + 1
            concept = json.loads(raw[s:e])
            concept.setdefault("genre_label", "lo-fi hip hop")
            concept.setdefault("tags_extra",  [])
            concept.setdefault("city",        None)
            concept.setdefault("aesthetic",   None)
            print(f"  [Gemini] concept: {concept.get('concept', '')[:80]}")
            return concept
        except Exception as ex:
            print(f"  [Gemini concept] failed ({ex}), trying next key")
    return None


def build_title_groq(concept: dict, duration: str, trends: dict | None = None) -> str | None:
    """
    Use Groq to generate a trend-aware YouTube title that balances SEO + emotional hook.
    Falls back to None (caller will use static pattern generator).
    """
    if not GROQ_KEY:
        return None
    try:
        from groq import Groq
        client   = Groq(api_key=GROQ_KEY)
        dur_str  = DURATION_DISPLAY.get(duration, duration)
        season   = trends.get("season", "") if trends else ""
        trend_titles = (trends.get("trending_titles", [])[:6] if trends else [])

        trend_ctx = ""
        if trend_titles:
            trend_ctx = "Top-performing titles this week (DO NOT copy — use as pattern inspiration):\n"
            trend_ctx += "\n".join(f"  • {t[:70]}" for t in trend_titles)
            trend_ctx += "\n\n"
        if season:
            trend_ctx += f"Current season: {season}.\n"

        prompt = f"""\
Write ONE YouTube title for a lofi music video. It should feel like something a real person \
would write in their notes app at 2am — specific, a little cinematic, not trying too hard.

{trend_ctx}Concept: {concept.get('concept', '')}
Mood: {concept.get('mood_line', '')}
Activity: {concept.get('activity', '')}
Duration: {dur_str}
Genre: {concept.get('genre_label', 'lo-fi hip hop')}
City: {concept.get('city') or 'none'}
Time: {concept.get('time_label', '')}

[UNIQUENESS SEED: {random.randint(0, 1000000)}]
Use this seed to explore a different title structure or hook than previous attempts.

What a great title does:
- Captures a MOMENT, not a category ("you said five more minutes 40 minutes ago" > "late night focus")
- Uses an unexpected structure — not always [keyword] · [duration] · [thing]
- Duration can go at the end, in parentheses, or mid-sentence — not always slot 2
- The SEO keyword (lofi/study music) appears early but doesn't have to open the sentence
- Reads like something you'd actually say, not a metadata label

Structures to try (pick one that fits the concept):
"lofi hip hop · [scene], [observation] — {dur_str}"
"study music · [specific moment] ({dur_str})"
"lofi · {dur_str} · [action]. [short consequence]."
"lofi hip hop · [twist on expectation] · {dur_str}"
"lofi · [specific image], [specific image] — {dur_str} 🌙"

Hard rules:
1. "lofi", "lofi hip hop", or "study music" in the first 35 characters
2. Include {dur_str}
3. Total length 50-70 characters. Target 55-65.
   CRITICAL: first 40 characters must carry the complete hook — mobile truncates there.
   Make char 1-40 self-contained. Extend with duration/context after char 40.
   Do NOT pad with filler words to hit 65+ chars — hook quality matters more than length.
4. One emoji max, not at the start
5. No ALL CAPS, no "...", no "vibes", no "chill out", no "relax"
6. The interesting part must come from the CONCEPT, not filler words

Output ONLY the title — no quotes, no explanation."""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,   # higher = more creative, narrative variety
        )
        title = resp.choices[0].message.content.strip().strip('"').strip("'")
        if len(title) > 100:
            print(f"  [Groq] title too long ({len(title)} chars, YouTube limit 100), using pattern fallback")
            return None
        # Validate SEO rule 1: "lofi", "lo-fi", or "study music" must be in first 35 chars
        _SEO_KEYWORDS = ("lofi", "lo-fi", "study music", "lofi hip hop", "chillhop")
        title_prefix = title[:35].lower()
        if not any(kw in title_prefix for kw in _SEO_KEYWORDS):
            print(f"  [Groq] title fails SEO check (no lofi/study keyword in first 35 chars): '{title[:50]}...'")
            return None
        print(f"  [Groq] title: {title}")
        return title
    except Exception as ex:
        print(f"  [Groq title] failed ({ex}), using pattern generator")
        return None


def _pillar_weights() -> dict[str, float]:
    """
    Per-pillar weight multipliers derived from analytics_log.json.
    High-performing pillars get up to 2x weight; low performers get 0.5x.
    Falls back to uniform 1.0 if fewer than 5 samples per pillar exist.

    Thin wrapper kept for pick_concept_from_pool()'s call site -- the real
    implementation is scripts/analytics.py's pillar_weights(), which is now
    backed by a Beta-Bernoulli Thompson Sampling bandit (scripts/bandit.py)
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


def generate_title_variants(
    concept: dict,
    duration: str,
    trends: dict | None = None,
    n: int = 3,
) -> list[str]:
    """Return up to n unique title candidates for this concept. Procedural
    template-pattern titles (build_title) are primary; Groq is only used as
    an explicit opt-in failsafe (LOFI_LLM_FAILSAFE=1)."""
    variants: list[str] = []

    attempts = 0
    while len(variants) < n and attempts < 12:
        candidate = build_title(concept, duration)
        if candidate not in variants:
            variants.append(candidate)
        attempts += 1

    if len(variants) < n and os.getenv("LOFI_LLM_FAILSAFE") == "1":
        groq_title = build_title_groq(concept, duration, trends)
        if groq_title and groq_title not in variants:
            variants.append(groq_title)

    return variants[:n]


def pick_concept_from_pool() -> dict:
    """Combinatorial concept from the fallback pools."""
    _pw      = _pillar_weights()
    _pillars = list(_pw.keys())
    pillar   = random.choices(_pillars, weights=[_pw[p] for p in _pillars], k=1)[0]
    act      = random.choice(ACTIVITY_POOL)
    time_  = random.choice(TIME_POOL)

    if pillar == "temporal":
        time2 = random.choice(TIME_POOL)
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
            "concept":     f"lofi for the {emo[0]} — {emo[1][:60]}",
            "city":        None,
            "setting":     "wherever you are",
            "time_label":  time_[0],
            "mood_line":   emo[1][:60],
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
    """Get a concept — procedural pool (analytics-weighted, hundreds of hand-
    written combinations) is primary and always used. Gemini/Groq are only
    ever reached as an explicit opt-in failsafe (LOFI_LLM_FAILSAFE=1)."""
    if os.getenv("LOFI_LLM_FAILSAFE") == "1":
        concept = pick_concept_gemini(trends) or pick_concept_groq(trends)
        if concept:
            return concept
    return pick_concept_from_pool()


# Maps internal sub_genre keys → SEO genre_label strings used in titles/descriptions.
# Any sub_genre not in this dict falls back to "lo-fi hip hop".
_SUBGENRE_TO_GENRE_LABEL: dict[str, str] = {
    "dark_lofi":      "dark lofi",
    "lofi_phonk":     "dark lofi",
    "vaporwave":      "lofi ambient",
    "ambient":        "lofi ambient",
    "lofi_jazz":      "lofi jazz",
    "jazz_cafe":      "lofi jazz",
    "nujabes":        "lofi jazz",
    "neo_soul":       "neo-soul lofi",
    "bossa_lofi":     "bossa nova lofi",
    "lofi_rnb":       "neo-soul lofi",
    "chillhop":       "chillhop",
    "hip_hop_lofi":   "lo-fi hip hop",
    "lo_fi_funk":     "lo-fi hip hop",
    "chill_beats":    "chillhop",
    "lofi_house":     "city pop lofi",
    "cozy_cafe":      "lo-fi hip hop",
    "morning_lofi":   "lo-fi hip hop",
    "anime_lofi":     "lofi jazz",
    "summer_vibes":   "city pop lofi",
    "bedroom_pop":    "lo-fi hip hop",
    "city_pop":       "city pop lofi",
    "study_lofi":     "lo-fi hip hop",
    "piano_lofi":     "lofi jazz",
    "lofi_classical": "lofi ambient",
}


def concept_from_music_params(music_sub_genre: str, music_mood: str, base_concept: dict) -> dict:
    """
    Return a copy of base_concept with genre_label and mood_line overridden
    to match what was actually generated. Called after generate_tracks() so
    SEO titles reflect the real music, not the pre-generation guess.
    """
    updated = dict(base_concept)
    genre_label = _SUBGENRE_TO_GENRE_LABEL.get(music_sub_genre)
    if genre_label:
        updated["genre_label"] = genre_label
    if music_mood and len(music_mood.split()) >= 3:
        updated["mood_line"] = music_mood
    return updated


# ──────────────────────────────────────────────────────────────────────────────
#  TITLE BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def build_title(concept: dict, duration: str) -> str:
    dur_str  = DURATION_DISPLAY.get(duration, duration)
    pillar   = concept.get("pillar", "temporal")
    city     = concept.get("city") or "city"
    setting  = concept.get("setting", "room")
    time_l   = concept.get("time_label", "late night")
    activity = concept.get("activity", "study")
    mood      = concept.get("mood_line", "chill")
    aesthetic = concept.get("aesthetic", "cozy")
    genre     = concept.get("genre_label", "lo-fi hip hop")
    # Derive a clean short adjective for emotional patterns.
    # mood_line is often a poetic phrase — extract only the first 1-2 words
    # and map common phrases to clean adjectives.
    _EMO_MAP = [
        ("overwhelm",  "overwhelmed"), ("anxious",    "anxious"),
        ("burnt out",  "burnt out"),   ("burnout",    "burnt out"),
        ("lonely",     "lonely"),      ("alone",      "alone"),
        ("nostalgic",  "nostalgic"),   ("melancholy", "melancholy"),
        ("stressed",   "stressed"),    ("numb",       "numb"),
        ("hopeful",    "hopeful"),     ("motivated",  "motivated"),
        ("exhaust",    "exhausted"),   ("tired",      "tired"),
        ("sad",        "sad"),         ("lost",       "lost"),
        ("calm",       "calm"),        ("focused",    "focused"),
        ("grief",      "melancholy"),  ("weight",     "heavy-hearted"),
        ("quiet",      "quietly wired"), ("silence",  "silent"),
    ]
    mood_lower = mood.lower()
    emo = next((v for k, v in _EMO_MAP if k in mood_lower), "tired but focused")

    if pillar == "temporal":
        pattern = random.choice(TITLE_PATTERNS_TEMPORAL)
        title = pattern.format(time=time_l, activity=activity, duration=dur_str)
    elif pillar == "activity":
        pattern = random.choice(TITLE_PATTERNS_ACTIVITY)
        title = pattern.format(activity=activity, duration=dur_str)
    elif pillar == "emotional":
        pattern = random.choice(TITLE_PATTERNS_EMOTIONAL)
        title = pattern.format(emotional_state=emo, activity=activity,
                               time=time_l, duration=dur_str)
    elif pillar == "aesthetic":
        pattern = random.choice(TITLE_PATTERNS_AESTHETIC)
        title = pattern.format(aesthetic=aesthetic, activity=activity, duration=dur_str)
    else:  # cross_genre
        pattern = random.choice(TITLE_PATTERNS_CROSSGENRE)
        title = pattern.format(genre=genre, activity=activity, duration=dur_str)

    # Trim to 100 chars (YouTube hard limit) at a word boundary
    if len(title) > 100:
        title = title[:100].rsplit(" ", 1)[0].rstrip(" ·—,-")
    return title


# ──────────────────────────────────────────────────────────────────────────────
#  DESCRIPTION BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def build_description(concept: dict, duration: str) -> str:
    city     = concept.get("city") or ""
    time_l   = concept.get("time_label", "")
    mood     = concept.get("mood_line", "chill")
    activity = concept.get("activity", "work")
    genre    = concept.get("genre_label", "lo-fi hip hop")
    setting  = concept.get("setting", "room")

    city_phrase  = f"Somewhere in {city}" if city else "wherever you are"
    time_phrase  = time_l if time_l else "late"

    # Fill concept with formatting helpers
    concept_ctx = dict(concept)
    concept_ctx["city_phrase"]  = city_phrase
    concept_ctx["time_phrase"]  = time_phrase
    concept_ctx["duration"]     = DURATION_DISPLAY.get(duration, duration)

    # Mood hook line (atmospheric, goes AFTER the SEO-first opening)
    hook_template = random.choice(DESCRIPTION_HOOKS)
    try:
        mood_hook = hook_template.format(**concept_ctx)
    except KeyError:
        mood_hook = mood

    # Setting story paragraph
    setting_story = _build_setting_story(concept_ctx)

    # Chapters
    chapters = _build_chapters(duration, concept)
    chapters_str = "\n".join(f"{ts} — {label}" for ts, label in chapters)

    # Hashtags: first 3 appear ABOVE the video title on watch page — high-traffic only.
    # Hardcoded pool ensures lofi/studymusic always appear; duration tag as third.
    _HTAG_POOL = ["studymusic", "lofihiphop", "lofibeats", "chillhop", "focusmusic",
                  "studylofi", "lofimusic", "chillbeats"]
    dur_tags = TAGS_DURATION.get(duration, [])
    dur_htag = _clean_tag(dur_tags[0]).replace(" ", "") if dur_tags else "lofi3hours"
    _htag_candidates = _HTAG_POOL[:]
    random.shuffle(_htag_candidates)
    tag1 = _htag_candidates[0]
    tag2 = _htag_candidates[1]
    tag3 = dur_htag

    desc = DESCRIPTION_BODY.format(
        duration=DURATION_DISPLAY.get(duration, duration),
        genre_label=genre,
        activity=activity,
        mood_hook=mood_hook,
        setting_story=setting_story,
        chapters=chapters_str,
        tag1=tag1, tag2=tag2, tag3=tag3,
    )
    # Guard: YouTube's hard limit is 60 hashtags (exceeding it silences all hashtags).
    # Cap at 5 because 3-5 is the optimal range for discovery.
    _htag_count = len(re.findall(r'#\w+', desc))
    if _htag_count > 5:
        _found = 0
        def _htag_filter(m):
            nonlocal _found
            _found += 1
            return m.group(0) if _found <= 5 else ""
        desc = re.sub(r'#\w+', _htag_filter, desc)
    return desc[:4900]   # YouTube hard limit is 5000 chars; leave buffer


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def generate_seo(theme_name: str = None, duration: str = None,
                 use_ollama: bool = False, concept: dict = None,
                 trends: dict | None = None) -> tuple:
    """
    Generate SEO metadata for a video.

    Args:
        theme_name: Visual theme (cozy_rain, purple_dusk, etc.)
        duration:   Video duration label ("1 hour", "2 hours", etc.)
        use_ollama: Use local Ollama to polish description
        concept:    Pre-generated concept dict (pass from run.py to avoid double Groq call)
        trends:     TrendSnapshot from trend_research.get_trend_snapshot()

    Returns: (seo_dict, seo_file_path)
    """
    duration = duration or "2 hours"

    # Get or generate concept (trend-aware)
    if concept is None:
        print("  [SEO] Generating concept...")
        concept = pick_concept(trends)

    # Generate 3 title variants; pick one for upload diversity tracking, weighted
    # by past per-slot CTR for this pillar once enough data exists (same
    # 0.5x-2.0x/needs-5-samples pattern as _pillar_weights()) -- falls back to
    # uniform random for any variant slot without performance data yet.
    title_variants  = generate_title_variants(concept, duration, trends, n=3)
    from scripts.analytics import title_variant_weights as _title_variant_weights
    _tvw = _title_variant_weights().get(concept.get("pillar"), [])
    _weights = (_tvw + [1.0] * len(title_variants))[:len(title_variants)]
    chosen_idx      = random.choices(range(len(title_variants)), weights=_weights, k=1)[0]
    title           = title_variants[chosen_idx]
    description = build_description(concept, duration)
    tags        = build_tags(concept, duration, theme_name=theme_name)

    # Inject trending tags if available — lofi-relevant only, no cross-genre pollution
    if trends:
        _LOFI_ALLOW = {
            "lofi", "lo-fi", "lo fi", "chill", "study", "focus", "ambient",
            "jazz", "beats", "hip hop", "hiphop", "relax", "sleep", "night",
            "rain", "chillhop", "vaporwave", "phonk", "bossa", "neo soul",
            "bedroom", "music", "instrumental", "playlist", "2025", "2026",
        }
        existing_lower = {t.lower() for t in tags}
        yt_tags = [
            _clean_tag(t) for t in trends.get("trending_tags", [])
            if any(kw in t.lower() for kw in _LOFI_ALLOW)
            and _clean_tag(t).lower() not in existing_lower
        ][:3]
        combined = tags + yt_tags
        seen: set[str] = set()
        merged: list[str] = []
        total_chars = 0
        for t in combined:
            tl = t.lower()
            char_cost = len(t) + (1 if merged else 0)
            if tl not in seen and total_chars + char_cost <= 490:
                seen.add(tl)
                merged.append(t)
                total_chars += char_cost
        tags = merged

    if use_ollama:
        try:
            import subprocess
            result = subprocess.run(
                ["ollama", "run", "llama3.2",
                 f"Rewrite this YouTube description to be more evocative and atmospheric "
                 f"for a lo-fi music channel. Keep chapter timestamps exactly as-is. "
                 f"Under 500 chars total. Original:\n\n{description[:600]}"],
                capture_output=True, text=True, timeout=40,
            )
            if result.returncode == 0 and len(result.stdout.strip()) > 80:
                description = result.stdout.strip()
        except Exception:
            pass

    _now_utc = datetime.datetime.now(datetime.timezone.utc)
    ts = _now_utc.strftime("%Y%m%d_%H%M%S")
    # Unique ref stamped into description — used for cross-device duplicate detection.
    # YouTube search doesn't support description search, so we list recent videos and
    # grep descriptions ourselves. The ref is invisible to viewers (end of description).
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
        "generated_at":     _now_utc.isoformat(),
        "ref_id":           ref_id,
        "title_variants":   title_variants,
        "title_chosen_idx": chosen_idx,
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
    seo, path = generate_seo(theme, duration, use_ollama=False)
    print("\n--- CONCEPT ---")
    print(seo["concept"])
    print("\n--- TITLE ---")
    print(seo["title"])
    print("\n--- DESCRIPTION ---")
    print(seo["description"])
    print("\n--- TAGS ---")
    print(seo["tags"])
