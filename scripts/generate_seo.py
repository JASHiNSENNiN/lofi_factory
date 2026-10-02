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

Concepts come from a combinatorial pool of hand-written phrases (300+
base combinations); nothing here calls an external text generator.

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
     "small, close, a little out of focus. heard like a memory.",
     ["bedroom pop lofi", "indie lofi", "guitar lofi", "diy study music", "bedroom lofi"]),
    ("lofi rnb",
     "old soul records at midnight. muffled through the walls.",
     ["lofi rnb", "soul lofi", "rnb study music", "r&b lofi beats", "neo soul lofi"]),
]

# ──────────────────────────────────────────────────────────────────────────────
#  TITLE TEMPLATES  (100+ combinations guaranteed per concept)
# ──────────────────────────────────────────────────────────────────────────────

# Title patterns — varied structure, duration placement, separators, and story-first hooks
# Rule: "lofi", "lo-fi", or "study music" must appear within the first 35 characters.
# Vary the skeleton: don't always use [keyword] · {duration} · [thing].
#
# HOOK STRATEGIES — each pillar's patterns are grouped into distinct rhetorical
# families (not just reshuffled wording of the same idea):
#   "statement"     — descriptive, straightforward. States the scene/mood
#                      plainly and lets the concept carry the click.
#   "benefit_list"  — keyword-first + a benefit/activity keyword list
#                      (study/focus/relax/sleep), matching the verified
#                      convention real lofi/ambient-radio channels use (e.g.
#                      "lofi hip hop radio - beats to relax/study to").
#                      Replaced the old "curiosity_gap" family, which
#                      borrowed vlog-clickbait phrasing ("nobody tells you",
#                      "turns out X actually helps") that doesn't match this
#                      genre's search/browse-driven audience intent -- and
#                      reads as templated/repetitive at scale (YouTube's
#                      "inauthentic content" policy risk).
#   "spec_led"      — leads with a concrete number/fact (usually the duration)
#                      instead of mood language — a "specificity" hook that
#                      trades atmosphere for a hard, scannable fact up front.
#
# generate_title_variants() draws exactly one title per strategy so the 3
# variants it returns are genuinely different hooks, not 3 rolls of the same
# skeleton family.
HOOK_STRATEGIES = ("statement", "benefit_list", "spec_led")

# {genre} appears in 2 of each strategy's 4 templates below (the other 2 stay
# genre-free for stylistic variety, so not every title is genre-stuffed) --
# always paired with a literal "lofi"/"lo-fi"/"study music" token kept
# separate from {genre} itself, never relying on {genre} alone to satisfy
# that rule (some genre_label values, e.g. "chillhop", don't contain "lofi").
TITLE_PATTERNS_TEMPORAL = {
    "statement": [
        "lofi hip hop · {genre}, it's {time} and you're still awake — {duration}",
        "study music · {time}, the deadline blinked first — {duration} 📚",
        "lofi · {genre}, {time}, headphones in, world out — {duration} 🎵",
        "lofi hip hop, {time}, still on {activity}, {duration}",
    ],
    "benefit_list": [
        "lofi hip hop · {genre} · {time} · {benefits} — {duration}",
        "lofi · {time} focus mix — {benefits} · {duration}",
        "study music · {genre} · {time}, {duration} to {benefits}",
        "lofi · {time} beats for {benefits} — {duration}",
    ],
    "spec_led": [
        "{duration} lofi hip hop · {genre} · {time}, {activity}",
        "{duration} of lofi for {time}, no filler",
        "{duration} · study music · {genre} · {time} focus block",
        "{duration} straight · lofi · {time}, {activity}",
    ],
}

TITLE_PATTERNS_ACTIVITY = {
    "statement": [
        "lofi hip hop · {genre}, put this on, start {activity}, check back in {duration}",
        "study music · {activity} until it clicks — {duration} 📚",
        "lofi · {genre}, headphones on, {activity} open, timer set — {duration}",
        "study lofi · {duration} of {activity}, no commentary",
    ],
    "benefit_list": [
        "lofi hip hop · {genre} · {activity} · {benefits} — {duration}",
        "lofi · beats for {activity} — {benefits} · {duration}",
        "study music · {genre} · {activity} session, {duration} to {benefits}",
        "lofi · {activity} beats for {benefits} — {duration}",
    ],
    "spec_led": [
        "{duration} lofi hip hop · {genre} · {activity} mix",
        "{duration} · {activity} · lofi, zero interruptions",
        "{duration} of lofi · {genre} · built for {activity}",
        "{duration} · lofi · {activity} session, start to finish",
    ],
}

TITLE_PATTERNS_EMOTIONAL = {
    "statement": [
        "lofi hip hop · {genre}, {emotional_state} but the cursor is moving again — {duration}",
        "study music · for the {emotional_state} ones still at their desk — {duration} 🌙",
        "lofi · {genre}, {emotional_state} and somehow still on {activity} — {duration}",
        "lofi hip hop · {duration} · {emotional_state}. working anyway.",
    ],
    "benefit_list": [
        "lofi hip hop · {genre} for the {emotional_state} — {benefits} · {duration}",
        "lofi · {emotional_state} focus mix — {benefits} ({duration})",
        "study music · {genre} · {emotional_state}, still working — {benefits} · {duration}",
        "lofi · {emotional_state} beats to {benefits} — {duration}",
    ],
    "spec_led": [
        "{duration} lofi · {genre} for {emotional_state} focus",
        "{duration} · {emotional_state}, working anyway · lofi",
        "{duration} of lofi · {genre} · made for {emotional_state} nights",
        "{duration} · study music · {emotional_state} but productive",
    ],
}

TITLE_PATTERNS_AESTHETIC = {
    "statement": [
        "lofi hip hop · {genre}, {aesthetic} light, {activity} open — {duration}",
        "study music · {aesthetic} energy study block — {duration} 📚",
        "lofi · {genre}, {aesthetic} room, see what happens — {duration}",
        "lofi hip hop · {aesthetic} focus session ({duration}, no breaks)",
    ],
    "benefit_list": [
        "lofi hip hop · {genre} · {aesthetic} · {benefits} — {duration}",
        "lofi · {aesthetic} beats for {benefits} — {duration}",
        "study music · {genre} · {aesthetic} focus session · {duration}",
        "lofi · {aesthetic}, {duration} to {benefits}",
    ],
    "spec_led": [
        "{duration} lofi · {genre} · {aesthetic} aesthetic, {activity}",
        "{duration} of {aesthetic} lofi for {activity}",
        "{duration} · {genre} · {aesthetic} · lofi hip hop",
        "{duration} straight of {aesthetic} lofi",
    ],
}

TITLE_PATTERNS_CROSSGENRE = {
    "statement": [
        "lofi hip hop · what if {genre} never left the library — {duration}",
        "study music · {genre} roots, lofi filter, {activity} session — {duration} 🎵",
        "lofi · {genre} but quieter, {duration} to {activity}",
        "lofi hip hop · the {genre} {activity} playlist ({duration})",
    ],
    "benefit_list": [
        "lofi hip hop · {genre} · {benefits} — {duration}",
        "lofi · {genre} beats for {benefits} — {duration}",
        "study music · {genre} roots, {duration} to {benefits}",
        "lofi · {genre}, {benefits} — {duration}",
    ],
    "spec_led": [
        "{duration} of {genre} lofi for {activity}",
        "{duration} · {genre} · lofi hip hop",
        "{duration} straight lofi · {genre}, one long set",
        "{genre} lofi · {duration} · {activity}",
    ],
}

_TITLE_PATTERNS_BY_PILLAR: dict[str, dict[str, list[str]]] = {
    "temporal":    TITLE_PATTERNS_TEMPORAL,
    "activity":    TITLE_PATTERNS_ACTIVITY,
    "emotional":   TITLE_PATTERNS_EMOTIONAL,
    "aesthetic":   TITLE_PATTERNS_AESTHETIC,
    "cross_genre": TITLE_PATTERNS_CROSSGENRE,
}

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

    # Dedupe and fill up to 490 chars (YouTube hard limit is 500; 10-char buffer).
    # Also enforce the per-tag cap here, not just in _clean_tag() -- the
    # TAGS_BROAD/TAGS_DURATION/TAGS_MID/TAGS_LONGTAIL static pools don't route
    # through _clean_tag, so this is the one choke point every candidate,
    # regardless of source, actually passes through before being sent upstream.
    seen: set[str] = set()
    out: list[str] = []
    total_chars = 0
    for t in candidates:
        t = t.strip()[:_MAX_TAG_CHARS].strip()
        if not t:
            continue
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
    "just {duration} of lofi, start to finish.",
    "{time_phrase}. {mood_line}.",
    "close the other tabs. this one stays.",
    "for the {activity} sessions that go longer than planned.",
    "{duration} of beats, start to finish.",
    "signal found. tuning in.",
    "ambient transmission from somewhere soft.",
    "the frequency is always on.",
    "{city_phrase}. {time_phrase}.",
    "for the ones still awake at this hour.",
    "{mood_line}. here's {duration}.",
]

DESCRIPTION_BODY = """
{genre_label} · {duration} for {activity}.

{mood_hook}

{setting_story}

⏱ CHAPTERS
{chapters}

─────────────────────────────────────
🔔 New lo-fi drops weekly — subscribe if this helped
👍 Like if this found you at the right time
💬 Tell me what you were working on in the comments

Original compositions, freshly composed and mixed for this upload.

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
            f"A {setting} in {city} at {time_}. {m} {dur} of steady focus.",
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


# Preferred title length band. Templates can't hit an exact length, so this
# is a preference when picking among candidates, not a hard limit.
_TITLE_TARGET_MIN, _TITLE_TARGET_MAX = 45, 70


def generate_title_variants(
    concept: dict,
    duration: str,
    trends: dict | None = None,
    n: int = 3,
) -> tuple[list[str], list[str]]:
    """Return up to n unique title candidates for this concept, each drawn
    from a DIFFERENT hook-strategy family (HOOK_STRATEGIES: "statement",
    "benefit_list", "spec_led") so the variants are genuinely different
    creative hooks -- not n rolls of the same skeleton family.

    Each attempt prefers a candidate landing in the [_TITLE_TARGET_MIN,
    _TITLE_TARGET_MAX] char range (falls back to the first deduped candidate
    if none of the 12 attempts land in range -- these pattern pools are
    small, so "best of a small set" rather than a guarantee).

    Returns (titles, strategies) -- two parallel lists, `strategies[i]` is
    the hook-strategy family `titles[i]` was built from. If n > len(
    HOOK_STRATEGIES), strategies repeat (cycled) for the extra slots.
    """
    variants: list[str] = []
    strategies: list[str] = []

    for i in range(n):
        strategy = HOOK_STRATEGIES[i % len(HOOK_STRATEGIES)]
        candidate = None
        for _attempt in range(12):
            cand = build_title(concept, duration, strategy=strategy, trends=trends)
            if cand not in variants:
                candidate = candidate or cand
                if _TITLE_TARGET_MIN <= len(cand) <= _TITLE_TARGET_MAX:
                    candidate = cand
                    break
        if candidate is None:
            # This strategy's small pattern set was exhausted by dedup --
            # fall back to any strategy rather than dropping the slot.
            for _attempt in range(12):
                cand = build_title(concept, duration, trends=trends)
                if cand not in variants:
                    candidate = candidate or cand
                    if _TITLE_TARGET_MIN <= len(cand) <= _TITLE_TARGET_MAX:
                        candidate = cand
                        break
        if candidate is not None:
            variants.append(candidate)
            strategies.append(strategy)

    return variants[:n], strategies[:len(variants[:n])]


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
    """Get a concept from the analytics-weighted procedural pool.

    `trends` is accepted for call-site compatibility and currently unused."""
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
    # 3 new research-driven subgenres (config/genres/README.md's "add a new
    # subgenre" step 2). Note: lofi_drill/lofi_world (added in a prior pass)
    # were never actually added here and silently fall back to "lo-fi hip
    # hop" -- that looks like an unintentional gap in that pass, not a
    # pattern worth repeating, so these 3 get real labels instead.
    "sleep_lofi":     "lofi ambient",
    "lofi_garage":    "lofi garage",
    "lofi_synthwave": "synthwave lofi",
}


def concept_from_music_params(music_sub_genre: str, music_mood: str, base_concept: dict) -> dict:
    """
    Return a copy of base_concept with genre_label and mood_line overridden
    to match what was actually generated. Called after generate_tracks() so
    SEO titles reflect the real music, not the pre-generation guess.

    Exception: the "cross_genre" pillar's genre_label is left untouched. Its
    concept came from a specific, curated CROSS_GENRE_POOL pick -- that pick
    IS the pillar's whole reason for existing, and overriding it with
    _SUBGENRE_TO_GENRE_LABEL's coarser alias would silently discard a more
    specific, deliberate choice in favor of a less specific one (confirmed
    2026-08-26: this was clobbering the pool's pick on every cross_genre
    video, making its title/concept mismatch).
    """
    updated = dict(base_concept)
    if base_concept.get("pillar") != "cross_genre":
        genre_label = _SUBGENRE_TO_GENRE_LABEL.get(music_sub_genre)
        if genre_label:
            updated["genre_label"] = genre_label
    if music_mood and len(music_mood.split()) >= 3:
        updated["mood_line"] = music_mood
    return updated


# ──────────────────────────────────────────────────────────────────────────────
#  TITLE BUILDER
# ──────────────────────────────────────────────────────────────────────────────

_BENEFIT_KEYWORDS = ["study", "focus", "relax", "sleep", "chill", "unwind"]


def _benefit_tail(trends: dict | None = None) -> str:
    """Comma-joined 2-3 word benefit-list tail for the "benefit_list" hook
    strategy, matching the verified lofi/ambient-radio convention
    (keyword-first + Study/Focus/Relax/Sleep list), e.g. real competitor
    titles already scraped into assets/trend_cache.json: "lofi hip hop
    radio - beats to relax/study to". Trend-aware when real competitor
    titles are available (ranks the vocabulary by what's actually showing up
    this week); falls back to a uniform-random sample otherwise.
    """
    if trends:
        from scripts.trend_research import extract_title_benefit_signals
        ranked = extract_title_benefit_signals(trends)
        if ranked:
            return ", ".join(ranked[:random.choice([2, 3])])
    return ", ".join(random.sample(_BENEFIT_KEYWORDS, random.choice([2, 3])))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower().replace("lo-fi", "lofi").replace("lo fi", "lofi")).strip()


def tidy_title(title: str) -> str:
    """Remove the repetition the pattern templates produce: a " · " segment
    already contained in another segment ("lofi hip hop · lo-fi hip hop, ...")
    and the same word twice in a row ("lofi lofi")."""
    segments = [seg for seg in title.split(" · ") if seg.strip()]
    kept: list[str] = []
    for i, seg in enumerate(segments):
        n = _norm(seg)
        others = [_norm(o) for j, o in enumerate(segments) if j != i]
        dup_later = any(n == o for o in others[i:])
        contained = n and any(n != o and re.search(rf"\b{re.escape(n)}\b", o) for o in others)
        if not dup_later and not contained:
            kept.append(seg)
    title = " · ".join(kept) if kept else title
    # "lofi lofi", "lo-fi lofi": drop the second of two equal adjacent words
    words = title.split(" ")
    out = [w for k, w in enumerate(words) if k == 0 or _norm(w) == "" or _norm(w) != _norm(words[k - 1])]
    return " ".join(out)


def build_title(concept: dict, duration: str, strategy: str | None = None,
                 trends: dict | None = None) -> str:
    """Build one title from the concept's pillar pattern set.

    `strategy` picks a specific hook-strategy family (one of HOOK_STRATEGIES:
    "statement", "benefit_list", "spec_led"). If omitted (or unrecognized),
    a pattern is drawn from the pooled union of all strategies for that
    pillar — this preserves the old flat-random behavior for any caller that
    doesn't care which hook family it gets.

    `trends` (optional) ranks the "benefit_list" strategy's keyword tail by
    real scraped competitor titles instead of a uniform-random sample -- see
    _benefit_tail(). Unused by patterns that don't reference {benefits}.
    """
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

    # Compute benefits (may itself draw from random.choice/random.sample)
    # BEFORE the pattern pick below, so the pattern-selection random.choice()
    # call stays the last one made in this function -- tests spy on
    # random.choice to verify which candidate pool a strategy drew from.
    format_kwargs = {
        "time": time_l, "activity": activity, "duration": dur_str,
        "emotional_state": emo, "aesthetic": aesthetic, "genre": genre,
        "benefits": _benefit_tail(trends),
    }

    patterns_by_strategy = _TITLE_PATTERNS_BY_PILLAR.get(pillar, TITLE_PATTERNS_TEMPORAL)
    if strategy in patterns_by_strategy:
        candidates = patterns_by_strategy[strategy]
    else:
        # Unknown/omitted strategy -- pool every strategy's patterns together
        # (preserves the old flat-random-across-all-10 behavior).
        candidates = [p for plist in patterns_by_strategy.values() for p in plist]
    pattern = random.choice(candidates)
    title = tidy_title(pattern.format(**format_kwargs))

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

    # Generate 3 title variants (one per hook-strategy family -- statement,
    # benefit_list, spec_led); pick one for upload diversity tracking,
    # weighted by TWO independent bandit signals multiplied together: past
    # per-hook-strategy performance for this pillar (title_variant_weights,
    # coarse -- "which creative hook family wins") and per-surface-text-
    # feature performance (title_feature_weights, finer -- "does a
    # target-length/emoji/benefit-list title win", mined from the same
    # already-logged title text). Both fall back to a neutral 1.0 for any
    # strategy/feature without >=5 samples of performance data yet.
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
