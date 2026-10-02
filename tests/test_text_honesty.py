"""What viewers read: no false claims, no repeated genre words, no thumbnail
text cut off mid-phrase, no fake LIVE badge or frozen clock in the video."""
import inspect
import io
import contextlib
import random
import re

from scripts import generate_seo as seo
from scripts import generate_thumbnail_cozy as thumb
from scripts.visual_v2 import scene

_FALSE_CLAIMS = re.compile(r"no ads|no interruptions|uninterrupted|no loop|recorded in|"
                           r"free to use|no copyright", re.IGNORECASE)


def _titles(n=200):
    out = []
    for i in range(n):
        random.seed(5000 + i)
        with contextlib.redirect_stdout(io.StringIO()):
            concept = seo.pick_concept_from_pool()
            out.append(seo.build_title(concept, random.choice(["1 hour", "2 hours"])))
    return out


def test_seo_text_makes_no_false_claims():
    assert not _FALSE_CLAIMS.search(inspect.getsource(seo))


def test_titles_do_not_repeat_the_genre_or_words():
    for t in _titles():
        low = t.lower().replace("lo-fi", "lofi")
        assert low.count("lofi hip hop") <= 1, t
        assert not re.search(r"\b(\w+) \1\b", low), t


def test_thumbnail_text_never_ends_mid_phrase():
    for t in _titles():
        short = thumb._derive_short_title(t)
        if short is None:
            continue
        last = short.split()[-1]
        assert last not in thumb._DANGLING, (t, short)
        assert not last.isdigit(), (t, short)
        assert len(short) <= thumb._SHORT_TITLE_MAX_CHARS


def test_video_header_has_no_live_badge_or_clock():
    src = inspect.getsource(scene.draw_header)
    assert not re.search(r'\.text\([^)]*"LIVE"', src)
    assert "strftime" not in src


def test_thumbnail_and_video_use_one_channel_name():
    src = inspect.getsource(thumb._draw_watermark)
    assert "CHANNEL_NAME" in src and "lofi factory" not in src
